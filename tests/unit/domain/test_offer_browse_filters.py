from app.domain.entities import Offer
from app.domain.matching import level_matches, text_matches, tech_stack_matches


def _offer(
    title: str = "Dev",
    company: str = "Acme",
    tech_stack: list[str] | None = None,
    tech_stack_nice_to_have: list[str] | None = None,
    levels: list[str] | None = None,
) -> Offer:
    return Offer(
        link="https://example.com",
        title=title,
        company=company,
        tech_stack=tech_stack or [],
        tech_stack_nice_to_have=tech_stack_nice_to_have or [],
        levels=levels or [],
    )


def test_tech_stack_matches_passes_when_no_techs_are_requested():
    assert tech_stack_matches(_offer(tech_stack=["Python"]), []) is True


def test_tech_stack_matches_passes_when_single_tech_is_in_required_stack():
    assert tech_stack_matches(_offer(tech_stack=["Python", "FastAPI"]), ["python"]) is True


def test_tech_stack_matches_passes_when_tech_is_in_nice_to_have_stack():
    assert tech_stack_matches(_offer(tech_stack_nice_to_have=["Docker"]), ["docker"]) is True


def test_tech_stack_matches_fails_when_tech_is_not_present():
    assert tech_stack_matches(_offer(tech_stack=["Java"]), ["python"]) is False


def test_tech_stack_matches_passes_when_all_requested_techs_are_present():
    assert tech_stack_matches(_offer(tech_stack=["Python", "Docker"]), ["python", "docker"]) is True


def test_tech_stack_matches_fails_when_any_requested_tech_is_missing():
    assert tech_stack_matches(_offer(tech_stack=["Python"]), ["python", "docker"]) is False


def test_text_matches_passes_when_no_search_is_requested():
    assert text_matches(_offer(title="Backend Engineer"), None) is True


def test_text_matches_passes_when_search_is_blank():
    assert text_matches(_offer(title="Backend Engineer"), "") is True


def test_text_matches_passes_when_search_matches_title_case_insensitively():
    assert text_matches(_offer(title="Backend Engineer"), "engineer") is True


def test_text_matches_passes_when_search_matches_company_case_insensitively():
    assert text_matches(_offer(company="Acme Corp"), "acme") is True


def test_text_matches_fails_when_search_matches_neither_title_nor_company():
    assert text_matches(_offer(title="Backend Engineer", company="Acme"), "frontend") is False


def test_level_matches_passes_when_no_levels_are_requested():
    assert level_matches(_offer(levels=["mid"]), []) is True


def test_level_matches_passes_when_single_level_matches_case_insensitively():
    assert level_matches(_offer(levels=["Mid", "Senior"]), ["mid"]) is True


def test_level_matches_fails_when_level_is_not_present():
    assert level_matches(_offer(levels=["Junior"]), ["senior"]) is False


def test_level_matches_fails_when_offer_has_no_levels():
    assert level_matches(_offer(levels=[]), ["mid"]) is False


def test_level_matches_passes_when_any_of_multiple_requested_levels_matches():
    assert level_matches(_offer(levels=["Senior"]), ["mid", "senior"]) is True


def test_level_matches_fails_when_none_of_multiple_requested_levels_match():
    assert level_matches(_offer(levels=["Junior"]), ["mid", "senior"]) is False
