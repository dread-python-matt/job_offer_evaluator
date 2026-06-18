import pytest

from app.domain.entities import Experience, Offer, Project, Skill, UserProfile


def test_skill_rejects_rating_below_1():
    with pytest.raises(ValueError):
        Skill(name="Python", rating=0)


def test_skill_rejects_rating_above_5():
    with pytest.raises(ValueError):
        Skill(name="Python", rating=6)


def test_skill_accepts_rating_in_range():
    skill = Skill(name="Python", rating=5)
    assert skill.name == "Python"
    assert skill.rating == 5


def test_project_holds_repository_summary_period_and_tech_stack():
    project = Project(
        name="Evaluator",
        repository_link="https://github.com/user/evaluator",
        summary="A job matching app",
        date_from="2026-01",
        date_to="2026-06",
        tech_stack=["Python", "FastAPI"],
    )
    assert project.repository_link == "https://github.com/user/evaluator"
    assert project.tech_stack == ["Python", "FastAPI"]


def test_experience_holds_description_period_and_tech_stack():
    experience = Experience(
        title="Backend Developer",
        company="Acme",
        description="Built APIs",
        date_from="2024-01",
        date_to="2025-12",
        tech_stack=["Python", "Postgres"],
    )
    assert experience.company == "Acme"
    assert experience.tech_stack == ["Python", "Postgres"]


def test_user_profile_aggregates_skills_summary_projects_and_experience():
    profile = UserProfile(
        summary="Backend developer",
        skills=[Skill(name="Python", rating=5)],
        projects=[
            Project(
                name="Evaluator",
                repository_link="link",
                summary="summary",
                date_from="2026-01",
                date_to="2026-06",
                tech_stack=["Python"],
            )
        ],
        experience=[
            Experience(
                title="Dev",
                company="Acme",
                description="desc",
                date_from="2024-01",
                date_to="2025-12",
                tech_stack=["Python"],
            )
        ],
    )
    assert profile.summary == "Backend developer"
    assert len(profile.skills) == 1
    assert profile.skill_names() == {"python"}


def test_offer_combines_required_and_nice_to_have_into_skill_set():
    offer = Offer(
        link="https://example.com/offer",
        title="Backend Developer",
        company="Acme",
        tech_stack=["Python", "FastAPI"],
        tech_stack_nice_to_have=["Docker"],
    )
    assert offer.skill_set() == {"python", "fastapi", "docker"}
