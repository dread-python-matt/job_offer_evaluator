from types import SimpleNamespace

import httpx
import openai
import pytest

from app.application.ports import ModelUsage, ModelUsageTracker
from app.domain.errors import AiScoringError
from app.domain.entities import Experience, Offer, Project, Skill, UserProfile
from app.infrastructure.llm_scoring_strategy import AgentScore, LLMScoringStrategy
from app.infrastructure.llm_utils import company_from_model


class FakeModelUsageTracker(ModelUsageTracker):
    def __init__(self) -> None:
        self.recorded: list[ModelUsage] = []

    def record(self, usage: ModelUsage) -> None:
        self.recorded.append(usage)

    def flush(self) -> list[ModelUsage]:
        flushed, self.recorded = self.recorded, []
        return flushed


def _fake_run_with_usage(rate: int, input_tokens: int = 100, output_tokens: int = 50):
    """Like _fake_run but adds context_wrapper.usage so tracking can be tested."""
    captured = {}

    def run(agent, prompt):
        captured["agent"] = agent
        captured["prompt"] = prompt
        return SimpleNamespace(
            final_output=AgentScore(rate=rate, pros=[], cons=[], rate_reason="ok"),
            context_wrapper=SimpleNamespace(
                usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
            ),
        )

    return run, captured


def _fake_run(rate: int, pros: list[str] | None = None, cons: list[str] | None = None, rate_reason: str = "good fit"):
    captured = {}

    def run(agent, prompt):
        captured["agent"] = agent
        captured["prompt"] = prompt
        return SimpleNamespace(
            final_output=AgentScore(
                rate=rate,
                pros=pros or [],
                cons=cons or [],
                rate_reason=rate_reason,
            )
        )

    return run, captured


def _fake_run_with_translator(rate: int, translated_text: str):
    """Returns a run callable that dispatches on agent identity:
    translator_agent calls return a translated string; all others return AgentScore."""
    translator_agent = object()
    calls: list[dict] = []

    def run(agent, prompt):
        calls.append({"agent": agent, "prompt": prompt})
        if agent is translator_agent:
            return SimpleNamespace(final_output=translated_text)
        return SimpleNamespace(
            final_output=AgentScore(rate=rate, pros=[], cons=[], rate_reason="ok")
        )

    return translator_agent, run, calls


def _candidate() -> UserProfile:
    return UserProfile(
        summary="Backend developer with 5 years of experience",
        skills=[Skill(name="Python", rating=5)],
        projects=[
            Project(
                name="Evaluator",
                repository_link="",
                summary="Built a job matching platform",
                date_from="",
                date_to="",
                tech_stack=["Python", "FastAPI"],
            )
        ],
        experience=[
            Experience(
                title="Backend Engineer",
                company="Acme",
                description="",
                date_from="",
                date_to="",
                tech_stack=["Python", "Postgres"],
            )
        ],
    )


def _offer() -> Offer:
    return Offer(
        link="https://example.com",
        title="Backend Developer",
        company="Acme",
        tech_stack=["Python"],
        tech_stack_nice_to_have=["Postgres"],
        description="Looking for a backend developer skilled in Python and FastAPI.",
    )


def test_description_score_is_derived_from_the_agents_rate():
    run, _ = _fake_run(rate=5)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    score = strategy.score(_candidate(), _offer())

    assert score.get("description") == 1.0


def test_lowest_agent_rate_gives_the_lowest_description_score():
    run, _ = _fake_run(rate=1)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    score = strategy.score(_candidate(), _offer())

    assert score.get("description") == 0.2


def test_skills_score_comes_from_the_skill_based_scorer():
    run, _ = _fake_run(rate=5)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    score = strategy.score(_candidate(), _offer())

    # Python rated 5/5, practiced in a project/experience -> doubled weight -> 2.0
    # Postgres is nice-to-have but not a rated skill -> contributes 0.0
    assert score.get("skills") == pytest.approx(2.0)


def test_overall_score_weighs_skills_to_description_4_to_1():
    run, _ = _fake_run(rate=5)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    score = strategy.score(_candidate(), _offer())

    assert score.overall_score == pytest.approx((2.0 * 4 + 1.0) / 5)


def test_prompt_includes_summary_project_summaries_and_job_description():
    run, captured = _fake_run(rate=3)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    strategy.score(_candidate(), _offer())

    prompt = captured["prompt"]
    assert "Backend developer with 5 years of experience" in prompt
    assert "Built a job matching platform" in prompt
    assert "Looking for a backend developer skilled in Python and FastAPI." in prompt


def test_constructor_builds_agent_with_the_given_model_when_no_agent_is_passed():
    run, captured = _fake_run(rate=3)
    strategy = LLMScoringStrategy(model="gpt-test-model", run=run)

    strategy.score(_candidate(), _offer())

    assert captured["agent"].model == "gpt-test-model"
    assert captured["agent"].output_type is AgentScore


def test_constructor_uses_the_provided_agent_instead_of_building_one():
    sentinel_agent = object()
    run, captured = _fake_run(rate=3)
    strategy = LLMScoringStrategy(agent=sentinel_agent, run=run)

    strategy.score(_candidate(), _offer())

    assert captured["agent"] is sentinel_agent


def test_offer_description_is_passed_to_translator_before_scoring():
    translator_agent, run, calls = _fake_run_with_translator(rate=4, translated_text="English description")
    strategy = LLMScoringStrategy(agent=object(), run=run, translator_agent=translator_agent)

    strategy.score(_candidate(), _offer())

    translation_call = next(c for c in calls if c["agent"] is translator_agent)
    assert translation_call["prompt"] == _offer().description


def test_scoring_agent_receives_translated_description_not_original():
    polish_description = "Szukamy programisty backendowego z doświadczeniem w Pythonie."
    english_translation = "We are looking for a backend developer with Python experience."
    offer_in_polish = Offer(
        link="https://example.com",
        title="Backend Developer",
        company="Acme",
        description=polish_description,
    )
    translator_agent, run, calls = _fake_run_with_translator(rate=4, translated_text=english_translation)
    scoring_agent = object()
    strategy = LLMScoringStrategy(agent=scoring_agent, run=run, translator_agent=translator_agent)

    strategy.score(_candidate(), offer_in_polish)

    scoring_call = next(c for c in calls if c["agent"] is scoring_agent)
    assert english_translation in scoring_call["prompt"]
    assert polish_description not in scoring_call["prompt"]


def test_translation_is_skipped_when_no_translator_agent_is_provided():
    run, captured = _fake_run(rate=3)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    strategy.score(_candidate(), _offer())

    assert "Looking for a backend developer skilled in Python and FastAPI." in captured["prompt"]


def test_empty_description_is_not_sent_to_the_translator():
    translator_agent, run, calls = _fake_run_with_translator(rate=3, translated_text="")
    offer_without_description = Offer(link="https://example.com", title="Dev", company="Acme")
    strategy = LLMScoringStrategy(agent=object(), run=run, translator_agent=translator_agent)

    strategy.score(_candidate(), offer_without_description)

    translation_calls = [c for c in calls if c["agent"] is translator_agent]
    assert translation_calls == []


def test_usage_tracker_records_scoring_call_with_token_counts():
    run, _ = _fake_run_with_usage(rate=4, input_tokens=200, output_tokens=80)
    tracker = FakeModelUsageTracker()
    strategy = LLMScoringStrategy(agent=object(), run=run, usage_tracker=tracker)

    strategy.score(_candidate(), _offer())

    scoring_record = next(r for r in tracker.recorded if r.label == "scoring")
    assert scoring_record.input_tokens == 200
    assert scoring_record.output_tokens == 80


def test_usage_tracker_records_model_and_company_for_gemini():
    run, _ = _fake_run_with_usage(rate=4, input_tokens=100, output_tokens=50)
    tracker = FakeModelUsageTracker()
    strategy = LLMScoringStrategy(model="gemini-2.0-flash", run=run, usage_tracker=tracker)

    strategy.score(_candidate(), _offer())

    scoring_record = next(r for r in tracker.recorded if r.label == "scoring")
    assert scoring_record.model == "gemini-2.0-flash"
    assert scoring_record.company == "Google"


def test_usage_tracker_records_openai_company_for_gpt_model():
    run, _ = _fake_run_with_usage(rate=4, input_tokens=100, output_tokens=50)
    tracker = FakeModelUsageTracker()
    strategy = LLMScoringStrategy(model="gpt-4o", run=run, usage_tracker=tracker)

    strategy.score(_candidate(), _offer())

    scoring_record = next(r for r in tracker.recorded if r.label == "scoring")
    assert scoring_record.model == "gpt-4o"
    assert scoring_record.company == "OpenAI"


def test_usage_tracker_records_translation_call_separately():
    def run(agent, prompt):
        return SimpleNamespace(
            final_output="translated" if agent is translator_agent else AgentScore(rate=3, pros=[], cons=[], rate_reason="ok"),
            context_wrapper=SimpleNamespace(usage=SimpleNamespace(input_tokens=50, output_tokens=20)),
        )

    tracker = FakeModelUsageTracker()
    translator_agent = object()
    strategy = LLMScoringStrategy(
        agent=object(), run=run, translator_agent=translator_agent, usage_tracker=tracker
    )

    strategy.score(_candidate(), _offer())

    labels = [r.label for r in tracker.recorded]
    assert "translation" in labels
    assert "scoring" in labels


def test_usage_tracker_is_not_called_when_not_provided():
    run, _ = _fake_run(rate=3)
    strategy = LLMScoringStrategy(agent=object(), run=run)

    strategy.score(_candidate(), _offer())  # must not raise


def test_usage_tracker_is_skipped_when_sdk_returns_no_usage():
    def run(agent, prompt):
        return SimpleNamespace(
            final_output=AgentScore(rate=3, pros=[], cons=[], rate_reason="ok"),
            context_wrapper=SimpleNamespace(usage=None),
        )

    tracker = FakeModelUsageTracker()
    strategy = LLMScoringStrategy(agent=object(), run=run, usage_tracker=tracker)

    strategy.score(_candidate(), _offer())  # must not raise

    assert tracker.recorded == []


def test_score_raises_ai_scoring_error_when_api_call_fails():
    def failing_run(agent, prompt):
        raise openai.APIError("rate limit exceeded", httpx.Request("GET", "https://api.example.com"), body=None)

    strategy = LLMScoringStrategy(agent=object(), run=failing_run)

    with pytest.raises(AiScoringError):
        strategy.score(_candidate(), _offer())


# --- company_from_model ---


def test_company_from_model_returns_google_for_gemini_prefix():
    assert company_from_model("gemini-2.0-flash") == "Google"


def test_company_from_model_returns_openai_for_gpt_prefix():
    assert company_from_model("gpt-4o") == "OpenAI"


def test_company_from_model_returns_openai_for_o1_prefix():
    assert company_from_model("o1-mini") == "OpenAI"


def test_company_from_model_returns_openai_for_o3_prefix():
    assert company_from_model("o3-turbo") == "OpenAI"


def test_company_from_model_returns_openai_for_o4_prefix():
    assert company_from_model("o4-mini") == "OpenAI"


def test_company_from_model_returns_anthropic_for_claude_prefix():
    assert company_from_model("claude-sonnet-4-6") == "Anthropic"


def test_company_from_model_returns_unknown_for_unrecognised_model():
    assert company_from_model("llama-3-8b") == "Unknown"
