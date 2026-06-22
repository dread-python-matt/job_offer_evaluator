from app.domain.entities import Offer, UserProfile
from app.domain.matching import MatchCriteria
from app.infrastructure.offer_filters import ExpiredFilter


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _offer(expired: bool) -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme", expired=expired)


def _passes(expired: bool, include_expired: bool) -> bool:
    criteria = MatchCriteria(candidate=_candidate(), include_expired=include_expired)
    return ExpiredFilter().passes(_offer(expired), criteria)


def test_passes_for_non_expired_offers_by_default():
    assert _passes(expired=False, include_expired=False) is True


def test_fails_for_expired_offers_by_default():
    assert _passes(expired=True, include_expired=False) is False


def test_passes_for_expired_offers_when_explicitly_included():
    assert _passes(expired=True, include_expired=True) is True


def test_passes_for_non_expired_offers_when_expired_offers_are_included():
    assert _passes(expired=False, include_expired=True) is True
