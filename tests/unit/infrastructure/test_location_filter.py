from app.domain.entities import Offer, UserProfile
from app.domain.filters import MatchCriteria
from app.infrastructure.offer_filters import LocationFilter


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _offer(locations: list[str]) -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme", locations=locations)


def test_passes_when_no_location_is_requested():
    offer = _offer(["Warsaw"])

    criteria = MatchCriteria(candidate=_candidate(), location=None)

    assert LocationFilter().passes(offer, criteria) is True


def test_passes_when_requested_location_is_a_substring_of_an_offer_location():
    offer = _offer(["Warsaw, Poland"])

    criteria = MatchCriteria(candidate=_candidate(), location="warsaw")

    assert LocationFilter().passes(offer, criteria) is True


def test_passes_when_any_of_multiple_offer_locations_match():
    offer = _offer(["Remote", "Krakow"])

    criteria = MatchCriteria(candidate=_candidate(), location="krakow")

    assert LocationFilter().passes(offer, criteria) is True


def test_fails_when_no_offer_location_matches():
    offer = _offer(["Warsaw"])

    criteria = MatchCriteria(candidate=_candidate(), location="Berlin")

    assert LocationFilter().passes(offer, criteria) is False


def test_fails_when_offer_has_no_locations_and_one_is_requested():
    offer = _offer([])

    criteria = MatchCriteria(candidate=_candidate(), location="Warsaw")

    assert LocationFilter().passes(offer, criteria) is False
