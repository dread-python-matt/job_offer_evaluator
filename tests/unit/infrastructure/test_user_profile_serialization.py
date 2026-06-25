from dataclasses import replace

from app.domain.entities import (
    B2BTaxForm,
    Experience,
    Project,
    Skill,
    TaxSituation,
    UserProfile,
    ZusScheme,
)
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


def test_tax_situation_survives_a_dict_round_trip():
    profile = replace(
        _profile(),
        tax_situation=TaxSituation(under_26=True, is_student=True, applies_tax_credit=False),
    )

    assert profile_from_dict(profile_to_dict(profile)) == profile


def test_legacy_profile_without_tax_situation_loads_with_defaults():
    # Rows written before tax_situation existed have no such key — they must still load.
    legacy = {"summary": "x", "skills": [], "projects": [], "experience": []}

    assert profile_from_dict(legacy).tax_situation == TaxSituation()


def test_b2b_tax_settings_survive_a_dict_round_trip():
    profile = replace(
        _profile(),
        tax_situation=TaxSituation(
            b2b_tax_form=B2BTaxForm.LINIOWY, b2b_zus_scheme=ZusScheme.PREFERENTIAL
        ),
    )

    assert profile_from_dict(profile_to_dict(profile)) == profile


def test_unknown_b2b_enum_values_fall_back_to_defaults():
    raw = {
        "summary": "x",
        "skills": [],
        "projects": [],
        "experience": [],
        "tax_situation": {"b2b_tax_form": "bogus", "b2b_zus_scheme": "nope"},
    }

    situation = profile_from_dict(raw).tax_situation
    assert situation.b2b_tax_form == TaxSituation().b2b_tax_form
    assert situation.b2b_zus_scheme == TaxSituation().b2b_zus_scheme
