import pytest

from app.domain.entities import Experience, Offer, Project, Skill, UserProfile
from app.infrastructure.scoring_strategies import (
    SkillOverlapScoringStrategy,
    WeightedSkillScoringStrategy,
)


def _profile(*skill_names: str) -> UserProfile:
    return UserProfile(
        summary="",
        skills=[Skill(name=name, rating=3) for name in skill_names],
        projects=[],
        experience=[],
    )


def _rated_profile(skill_ratings: dict[str, int], projects=None, experience=None) -> UserProfile:
    return UserProfile(
        summary="",
        skills=[Skill(name=name, rating=rating) for name, rating in skill_ratings.items()],
        projects=projects or [],
        experience=experience or [],
    )


def _project(tech_stack: list[str]) -> Project:
    return Project(
        name="Side Project",
        repository_link="",
        summary="",
        date_from="",
        date_to="",
        tech_stack=tech_stack,
    )


def _experience(tech_stack: list[str]) -> Experience:
    return Experience(
        title="Dev",
        company="Acme",
        description="",
        date_from="",
        date_to="",
        tech_stack=tech_stack,
    )


def _offer(tech_stack, nice_to_have=None) -> Offer:
    return Offer(
        link="https://example.com",
        title="Dev",
        company="Acme",
        tech_stack=tech_stack,
        tech_stack_nice_to_have=nice_to_have or [],
    )


def test_skill_overlap_score_is_matched_over_total_required_skills():
    profile = _profile("Python", "FastAPI", "Docker", "SQL")
    offer = _offer(["Python", "FastAPI", "Docker", "SQL", "Kubernetes"])

    score = SkillOverlapScoringStrategy().score(profile, offer)

    assert score.skills_score == pytest.approx(0.8)


def test_skill_overlap_score_has_no_description_signal():
    profile = _profile("Python")
    offer = _offer(["Python"])

    score = SkillOverlapScoringStrategy().score(profile, offer)

    assert score.description_score == 0.0


def test_skill_overlap_score_matching_is_case_insensitive():
    profile = _profile("python")
    offer = _offer(["Python"])

    assert SkillOverlapScoringStrategy().score(profile, offer).skills_score == 1.0


def test_skill_overlap_score_combines_required_and_nice_to_have_skills():
    profile = _profile("Python", "Docker")
    offer = _offer(["Python"], nice_to_have=["Docker", "Kubernetes"])

    assert SkillOverlapScoringStrategy().score(profile, offer).skills_score == pytest.approx(2 / 3)


def test_skill_overlap_score_is_zero_when_offer_has_no_required_skills():
    profile = _profile("Python")
    offer = _offer([])

    assert SkillOverlapScoringStrategy().score(profile, offer).skills_score == 0.0


def test_skill_overlap_score_is_zero_when_no_skills_match():
    profile = _profile("Java")
    offer = _offer(["Python", "FastAPI"])

    assert SkillOverlapScoringStrategy().score(profile, offer).skills_score == 0.0


def test_overall_score_weighs_skills_to_description_4_to_1():
    profile = _profile("Python")
    offer = _offer(["Python"])

    score = SkillOverlapScoringStrategy().score(profile, offer)

    assert score.skills_score == 1.0
    assert score.description_score == 0.0
    assert score.overall_score == pytest.approx(0.8)


def test_weighted_score_averages_rating_over_5_across_required_skills():
    profile = _rated_profile({"Python": 5, "Java": 3})
    offer = _offer(["Python", "Java", "Go"])

    score = WeightedSkillScoringStrategy().score(profile, offer)

    assert score.skills_score == pytest.approx((1.0 + 0.6 + 0.0) / 3)
    assert score.description_score == 0.0


def test_weighted_score_is_zero_when_offer_has_no_required_skills():
    profile = _rated_profile({"Python": 5})
    offer = _offer([])

    assert WeightedSkillScoringStrategy().score(profile, offer).skills_score == 0.0


def test_weighted_score_adds_nice_to_have_using_the_same_equation():
    profile = _rated_profile({"Docker": 4})
    offer = _offer([], nice_to_have=["Docker", "Kubernetes"])

    score = WeightedSkillScoringStrategy().score(profile, offer)

    assert score.skills_score == pytest.approx((0.8 + 0.0) / 2)


def test_weighted_score_combines_required_and_nice_to_have_scores():
    profile = _rated_profile({"Python": 5, "Docker": 4})
    offer = _offer(["Python"], nice_to_have=["Docker"])

    score = WeightedSkillScoringStrategy().score(profile, offer)

    assert score.skills_score == pytest.approx(1.0 + 0.8)


def test_weighted_score_doubles_skills_evidenced_by_a_project():
    profile = _rated_profile({"Python": 5}, projects=[_project(["Python"])])
    offer = _offer(["Python"])

    score = WeightedSkillScoringStrategy().score(profile, offer)

    assert score.skills_score == pytest.approx(2.0)


def test_weighted_score_doubles_skills_evidenced_by_experience():
    profile = _rated_profile({"Python": 5}, experience=[_experience(["Python"])])
    offer = _offer(["Python"])

    score = WeightedSkillScoringStrategy().score(profile, offer)

    assert score.skills_score == pytest.approx(2.0)


def test_weighted_score_matching_is_case_insensitive():
    profile = _rated_profile({"python": 5}, projects=[_project(["PYTHON"])])
    offer = _offer(["Python"])

    assert WeightedSkillScoringStrategy().score(profile, offer).skills_score == pytest.approx(2.0)
