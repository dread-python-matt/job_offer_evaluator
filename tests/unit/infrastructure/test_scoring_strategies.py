import pytest

from app.domain.entities import Experience, Offer, Project, Skill, UserProfile
from app.infrastructure.scoring_strategies import SkillBasedScorer


def _rated_profile(
    skill_ratings: dict[str, int], projects=None, experience=None
) -> UserProfile:
    return UserProfile(
        summary="",
        skills=[
            Skill(name=name, rating=rating) for name, rating in skill_ratings.items()
        ],
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


def test_skill_based_score_averages_capped_weights_across_required_skills():
    # Un-evidenced self-claims, so the cap applies: Python 5/5 -> 0.6 (capped), Java 3/5 -> 0.6,
    # Go absent -> 0.0; averaged over the three required skills.
    profile = _rated_profile({"Python": 5, "Java": 3})
    offer = _offer(["Python", "Java", "Go"])

    score = SkillBasedScorer().score(profile, offer)

    assert score.get("skills") == pytest.approx((0.6 + 0.6 + 0.0) / 3)


def test_skill_based_score_is_zero_when_offer_has_no_required_skills():
    profile = _rated_profile({"Python": 5})
    offer = _offer([])

    assert SkillBasedScorer().score(profile, offer).get("skills") == 0.0


def test_skill_based_score_is_zero_when_no_skills_match():
    profile = _rated_profile({"Java": 3})
    offer = _offer(["Python"])

    assert SkillBasedScorer().score(profile, offer).get("skills") == 0.0


def test_skill_based_score_adds_nice_to_have_using_the_same_equation():
    profile = _rated_profile({"Docker": 4})
    offer = _offer([], nice_to_have=["Docker", "Kubernetes"])

    score = SkillBasedScorer().score(profile, offer)

    # Docker 4/5 un-evidenced is capped to 0.6; Kubernetes absent -> 0.0.
    assert score.get("skills") == pytest.approx((0.6 + 0.0) / 2)


def test_skill_based_score_combines_required_and_nice_to_have_scores():
    profile = _rated_profile({"Python": 5, "Docker": 4})
    offer = _offer(["Python"], nice_to_have=["Docker"])

    score = SkillBasedScorer().score(profile, offer)

    # Python 5/5 and Docker 4/5 are both un-evidenced, so each is capped to 0.6.
    assert score.get("skills") == pytest.approx(0.6 + 0.6)


def test_skill_based_score_doubles_skills_evidenced_by_a_project():
    profile = _rated_profile({"Python": 5}, projects=[_project(["Python"])])
    offer = _offer(["Python"])

    score = SkillBasedScorer().score(profile, offer)

    assert score.get("skills") == pytest.approx(2.0)


def test_skill_based_score_doubles_skills_evidenced_by_experience():
    profile = _rated_profile({"Python": 5}, experience=[_experience(["Python"])])
    offer = _offer(["Python"])

    score = SkillBasedScorer().score(profile, offer)

    assert score.get("skills") == pytest.approx(2.0)


def test_skill_based_score_matching_is_case_insensitive():
    profile = _rated_profile({"python": 5}, projects=[_project(["PYTHON"])])
    offer = _offer(["Python"])

    assert SkillBasedScorer().score(profile, offer).get("skills") == pytest.approx(2.0)


def test_overall_score_equals_the_skills_score_when_it_is_the_only_component():
    profile = _rated_profile({"Python": 5})
    offer = _offer(["Python"])

    score = SkillBasedScorer().score(profile, offer)

    # The single skills component is the whole score (relationship holds regardless of the
    # cap's exact value).
    assert score.overall_score == pytest.approx(score.get("skills"))


def test_skill_based_score_counts_an_evidenced_but_unrated_skill():
    # Practiced in a real project but never self-rated: it must still count (it used to
    # contribute 0 — exactly backwards, since evidence is the trustworthy signal).
    # EVIDENCED_BASELINE (0.8) doubled for evidence = 1.6.
    profile = _rated_profile({}, projects=[_project(["Python"])])
    offer = _offer(["Python"])

    assert SkillBasedScorer().score(profile, offer).get("skills") == pytest.approx(1.6)


def test_evidenced_skill_outweighs_an_unevidenced_self_claim():
    evidenced = _rated_profile({}, projects=[_project(["Go"])])
    self_claimed = _rated_profile({"Go": 5})
    offer = _offer(["Go"])

    evidenced_score = SkillBasedScorer().score(evidenced, offer).get("skills")
    self_claimed_score = SkillBasedScorer().score(self_claimed, offer).get("skills")

    assert evidenced_score > self_claimed_score  # 1.6 > 0.6 (self-claim capped)


def test_unevidenced_self_claim_is_capped():
    # A self-rating of 5/5 with no project/experience evidence would be 1.0 uncapped; the cap
    # reins it in to UNEVIDENCED_SELF_RATING_CAP (0.6), so confident claims need evidence to count.
    profile = _rated_profile({"Python": 5})
    offer = _offer(["Python"])

    assert SkillBasedScorer().score(profile, offer).get("skills") == pytest.approx(0.6)


def test_cap_is_a_ceiling_not_a_floor_for_low_self_ratings():
    # Below the cap a low self-rating is unchanged (2/5 -> 0.4): the cap only trims, never lifts.
    profile = _rated_profile({"Python": 2})
    offer = _offer(["Python"])

    assert SkillBasedScorer().score(profile, offer).get("skills") == pytest.approx(0.4)
