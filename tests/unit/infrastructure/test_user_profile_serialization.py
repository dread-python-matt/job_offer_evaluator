from app.domain.entities import Experience, Project, Skill, UserProfile
from app.infrastructure.postgres_user_profile_repository import profile_from_dict, profile_to_dict


def _profile() -> UserProfile:
    return UserProfile(
        summary="Backend developer",
        skills=[Skill(name="Python", rating=5), Skill(name="SQL", rating=4)],
        projects=[
            Project(
                name="Evaluator",
                repository_link="https://github.com/x/evaluator",
                summary="Job matching app",
                date_from="2026-01",
                date_to="2026-06",
                tech_stack=["Python", "FastAPI"],
            )
        ],
        experience=[
            Experience(
                title="Backend Engineer",
                company="Acme",
                description="Built APIs",
                date_from="2024-01",
                date_to="2025-12",
                tech_stack=["Python", "Postgres"],
            )
        ],
    )


def test_profile_survives_a_dict_round_trip():
    profile = _profile()

    assert profile_from_dict(profile_to_dict(profile)) == profile


def test_to_dict_is_json_safe():
    import json

    # Must serialize without custom encoders (it's stored in a JSON column).
    json.dumps(profile_to_dict(_profile()))
