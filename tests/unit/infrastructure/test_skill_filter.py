from app.domain.entities import Offer, Skill, UserProfile
from app.domain.filters import MatchCriteria
from app.infrastructure.offer_filters import SkillFilter


def _rated_profile(skill_ratings: dict[str, int]) -> UserProfile:
    return UserProfile(
        summary="",
        skills=[Skill(name=name, rating=rating) for name, rating in skill_ratings.items()],
        projects=[],
        experience=[],
    )


def _offer(tech_stack, nice_to_have=None) -> Offer:
    return Offer(
        link="https://example.com",
        title="Dev",
        company="Acme",
        tech_stack=tech_stack,
        tech_stack_nice_to_have=nice_to_have or [],
    )


def test_passes_when_skill_score_is_above_min_score():
    candidate = _rated_profile({"Python": 5})
    offer = _offer(["Python"])

    assert SkillFilter().passes(offer, MatchCriteria(candidate=candidate, min_score=0.5)) is True


def test_passes_when_skill_score_exactly_equals_min_score():
    candidate = _rated_profile({"Python": 5})
    offer = _offer(["Python"])

    assert SkillFilter().passes(offer, MatchCriteria(candidate=candidate, min_score=1.0)) is True


def test_fails_when_skill_score_is_below_min_score():
    candidate = _rated_profile({"Python": 1})
    offer = _offer(["Python"])

    assert SkillFilter().passes(offer, MatchCriteria(candidate=candidate, min_score=0.5)) is False


def test_fails_when_no_skills_match():
    candidate = _rated_profile({"Java": 5})
    offer = _offer(["Python"])

    assert SkillFilter().passes(offer, MatchCriteria(candidate=candidate, min_score=0.1)) is False


def test_passes_when_offer_has_no_required_skills_and_min_score_is_zero():
    candidate = _rated_profile({"Python": 5})
    offer = _offer([])

    assert SkillFilter().passes(offer, MatchCriteria(candidate=candidate, min_score=0.0)) is True
