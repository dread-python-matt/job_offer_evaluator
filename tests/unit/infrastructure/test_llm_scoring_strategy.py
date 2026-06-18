from types import SimpleNamespace

import pytest

from app.domain.entities import Experience, Offer, Project, Skill, UserProfile
from app.infrastructure.llm_scoring_strategy import AgentScore, LLMScoringStrategy


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
    strategy = LLMScoringStrategy(model="gpt-test-model")

    assert strategy._agent.model == "gpt-test-model"
    assert strategy._agent.output_type is AgentScore


def test_constructor_uses_the_provided_agent_instead_of_building_one():
    sentinel_agent = object()

    strategy = LLMScoringStrategy(agent=sentinel_agent)

    assert strategy._agent is sentinel_agent
