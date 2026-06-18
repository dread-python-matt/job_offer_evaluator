from collections.abc import Callable
from typing import Any

from agents import Agent, Runner
from pydantic import BaseModel, Field

from app.domain.entities import Offer, UserProfile
from app.domain.matching import Score, ScoringStrategy
from app.infrastructure.scoring_strategies import SkillOverlapScoringStrategy

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


class LLMScoringStrategy(ScoringStrategy):
    """Scores candidate/offer fit via an OpenAI Agent.

    Pass `model` to swap which model is used without touching the rest of the app
    (it also falls back to the SDK's OPENAI_DEFAULT_MODEL env var when omitted).
    Pass `agent` and/or `run` to fully control execution, e.g. to inject a fake in tests.
    """

    def __init__(
        self,
        model: str | None = None,
        agent: Agent | None = None,
        run: Callable[[Agent, str], Any] = Runner.run_sync,
        skills_scoring_strategy: ScoringStrategy | None = None,
    ) -> None:
        self._agent = agent or Agent(
            name="Offer Fit Scorer",
            model=model,
            instructions=_INSTRUCTIONS,
            output_type=AgentScore,
        )
        self._run = run
        self._skills_scoring_strategy = skills_scoring_strategy or SkillOverlapScoringStrategy()

    def score(self, candidate: UserProfile, offer: Offer) -> Score:
        result = self._run(self._agent, self._build_prompt(candidate, offer))
        agent_score: AgentScore = result.final_output
        skills_score = self._skills_scoring_strategy.score(candidate, offer).skills_score
        return Score(skills_score=skills_score, description_score=agent_score.rate * 20 / 100)

    @staticmethod
    def _build_prompt(candidate: UserProfile, offer: Offer) -> str:
        project_summaries = "; ".join(
            f"{project.name}: {project.summary}" for project in candidate.projects if project.summary
        )
        return (
            f"Candidate summary: {candidate.summary or 'none'}\n"
            f"Candidate project summaries: {project_summaries or 'none'}\n"
            f"Job description: {offer.description or 'none'}"
        )
