from collections.abc import Callable
from typing import Any

import openai
from agents import Agent, Runner
from pydantic import BaseModel, Field

from app.application.ports import AiScoringError, ModelUsage, ModelUsageTracker
from app.domain.entities import Offer, UserProfile
from app.domain.matching import MatchScore, OfferScorer, ScoreComponent
from app.infrastructure.scoring_strategies import SkillBasedScorer

def company_from_model(model: str) -> str:
    if model.startswith("gemini"):
        return "Google"
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "OpenAI"
    if model.startswith("claude"):
        return "Anthropic"
    return "Unknown"


_INSTRUCTIONS = (
    "You evaluate how well a candidate fits a job offer, based on the candidate's "
    "summary, their project summaries, and the job description. "
    "Rate the fit from 1 (poor) to 5 (excellent), and list the pros and cons that "
    "led to that rating, plus a short reason for the rating."
)


class AgentScore(BaseModel):
    rate: int = Field(ge=1, le=5)
    pros: list[str]
    cons: list[str]
    rate_reason: str


class LLMScoringStrategy(OfferScorer):
    """Scores candidate/offer fit via an OpenAI Agent.

    Pass `model` to swap which model is used without touching the rest of the app
    (it also falls back to the SDK's OPENAI_DEFAULT_MODEL env var when omitted).
    Pass `agent` and/or `run` to fully control execution, e.g. to inject a fake in tests.
    Pass `translator_agent` to translate the offer description to English before scoring;
    skipped when the description is empty.
    """

    def __init__(
        self,
        model: str | None = None,
        agent: Agent | None = None,
        run: Callable[[Agent, str], Any] = Runner.run_sync,
        skills_scorer: OfferScorer | None = None,
        translator_agent: Agent | None = None,
        usage_tracker: ModelUsageTracker | None = None,
    ) -> None:
        self._agent = agent or Agent(
            name="Offer Fit Scorer",
            model=model,
            instructions=_INSTRUCTIONS,
            output_type=AgentScore,
        )
        self._model = model or (getattr(agent, "model", None) or "")
        self._run = run
        self._skills_scorer = skills_scorer or SkillBasedScorer()
        self._translator_agent = translator_agent
        self._usage_tracker = usage_tracker

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        description = self._translate_to_english(offer.description)
        result = self._run_tracked(self._agent, self._build_prompt(candidate, description), "scoring")
        agent_score: AgentScore = result.final_output
        skills_score = self._skills_scorer.score(candidate, offer).get("skills") or 0.0
        description_score = agent_score.rate * 20 / 100
        return (
            MatchScore()
            .with_component(ScoreComponent(name="skills", value=skills_score, weight=4.0))
            .with_component(ScoreComponent(name="description", value=description_score, weight=1.0))
        )

    def _translate_to_english(self, description: str) -> str:
        if not self._translator_agent or not description:
            return description
        result = self._run_tracked(self._translator_agent, description, "translation")
        return result.final_output

    def _run_tracked(self, agent: Agent, prompt: str, label: str) -> Any:
        try:
            result = self._run(agent, prompt)
        except openai.APIError as exc:
            raise AiScoringError(str(exc)) from exc
        if self._usage_tracker:
            sdk_usage = result.context_wrapper.usage
            if sdk_usage is not None:
                self._usage_tracker.record(
                    ModelUsage(
                        label=label,
                        input_tokens=sdk_usage.input_tokens,
                        output_tokens=sdk_usage.output_tokens,
                        model=self._model,
                        company=company_from_model(self._model),
                    )
                )
        return result

    @staticmethod
    def _build_prompt(candidate: UserProfile, description: str) -> str:
        project_summaries = "; ".join(
            f"{project.name}: {project.summary}" for project in candidate.projects if project.summary
        )
        return (
            f"Candidate summary: {candidate.summary or 'none'}\n"
            f"Candidate project summaries: {project_summaries or 'none'}\n"
            f"Job description: {description or 'none'}"
        )
