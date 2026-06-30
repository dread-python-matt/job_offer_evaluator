from app.application.skill_canonicalization import SkillCanonicalizer
from app.domain.entities import Experience, Offer, Project, Skill, UserProfile
from app.domain.skills import CanonicalSkill, SkillNormalizer


class _FakeNormalizer(SkillNormalizer):
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def normalize(self, raw: str) -> CanonicalSkill:
        return CanonicalSkill(id=self._mapping.get(raw.lower(), raw.lower()))


def _project(tech: list[str]) -> Project:
    return Project(
        name="p",
        repository_link="",
        summary="",
        date_from="",
        date_to="",
        tech_stack=tech,
    )


def _experience(tech: list[str]) -> Experience:
    return Experience(
        title="t",
        company="c",
        description="",
        date_from="",
        date_to="",
        tech_stack=tech,
    )


def test_canonicalizes_skills_projects_and_experience_preserving_ratings():
    normalizer = _FakeNormalizer(
        {"js": "javascript", "react.js": "react", "py": "python"}
    )
    candidate = UserProfile(
        summary="",
        skills=[Skill(name="JS", rating=4)],
        projects=[_project(["React.js"])],
        experience=[_experience(["py"])],
    )

    result = SkillCanonicalizer(normalizer).canonicalize_candidate(candidate)

    assert result.skills[0].name == "javascript"
    assert result.skills[0].rating == 4  # rating preserved
    assert result.projects[0].tech_stack == ["react"]
    assert result.experience[0].tech_stack == ["python"]


def test_canonicalizes_offer_tech_stacks_but_leaves_other_fields():
    normalizer = _FakeNormalizer({"js": "javascript", "k8s": "kubernetes"})
    offer = Offer(
        link="l",
        title="t",
        company="c",
        tech_stack=["JS"],
        tech_stack_nice_to_have=["k8s"],
    )

    result = SkillCanonicalizer(normalizer).canonicalize_offer(offer)

    assert result.tech_stack == ["javascript"]
    assert result.tech_stack_nice_to_have == ["kubernetes"]
    assert result.link == "l"  # untouched


def test_no_normalizer_is_an_identity_passthrough():
    candidate = UserProfile(
        summary="", skills=[Skill(name="JS", rating=5)], projects=[], experience=[]
    )
    offer = Offer(link="l", title="t", company="c", tech_stack=["JS"])
    canonicalizer = SkillCanonicalizer()

    assert canonicalizer.canonicalize_candidate(candidate) is candidate
    assert canonicalizer.canonicalize_offer(offer) is offer
