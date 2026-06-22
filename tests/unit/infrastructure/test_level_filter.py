from app.domain.entities import Offer, UserProfile
from app.domain.matching import MatchCriteria
from app.infrastructure.offer_filters import LevelFilter


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _offer(levels: list[str]) -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme", levels=levels)


def test_passes_when_no_levels_are_requested():
    offer = _offer(["mid"])

    criteria = MatchCriteria(candidate=_candidate(), level=[])

    assert LevelFilter().passes(offer, criteria) is True


def test_passes_when_single_requested_level_matches_case_insensitively():
    offer = _offer(["Mid", "Senior"])

    criteria = MatchCriteria(candidate=_candidate(), level=["mid"])

    assert LevelFilter().passes(offer, criteria) is True


def test_passes_when_any_of_multiple_requested_levels_matches():
    offer = _offer(["Senior"])

    criteria = MatchCriteria(candidate=_candidate(), level=["mid", "senior"])

    assert LevelFilter().passes(offer, criteria) is True


def test_fails_when_no_offer_level_matches():
    offer = _offer(["Junior"])

    criteria = MatchCriteria(candidate=_candidate(), level=["senior"])

    assert LevelFilter().passes(offer, criteria) is False


def test_fails_when_offer_has_no_levels_and_levels_are_requested():
    offer = _offer([])

    criteria = MatchCriteria(candidate=_candidate(), level=["mid"])

    assert LevelFilter().passes(offer, criteria) is False
