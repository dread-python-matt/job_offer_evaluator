import pytest

from app.domain.entities import Offer, UserProfile
from app.domain.matching import MatchCriteria
from app.infrastructure.offer_filters import SalaryFilter


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _offer(salary_range: str | None) -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme", salary_range=salary_range)


def _passes(salary_range: str | None, min_salary: float | None) -> bool:
    criteria = MatchCriteria(candidate=_candidate(), min_salary=min_salary)
    return SalaryFilter().passes(_offer(salary_range), criteria)


def test_passes_when_no_minimum_salary_is_requested():
    assert _passes(None, min_salary=None) is True


# Real samples pulled from the live `offers` table, with their expected normalized
# monthly value (upper bound of the range, /hour and /day converted to monthly).
@pytest.mark.parametrize(
    ("salary_range", "expected_monthly"),
    [
        ("18000 - 22500 PLN/month", 22500),
        ("120 - 140 PLN/hour", 140 * 168),
        ("B2B: 5600 - 8800 PLN/month", 8800),
        ("145 - 155 PLN/day", 155 * 21),
        ("11000 PLN", 11000),
        ("PERMANENT: 10000 PLN/month", 10000),
        # picks the best (highest) of multiple contract-type segments
        ("B2B: 6720 - 10080 PLN/month; ZLECENIE: 6720 - 8400 PLN/month", 10080),
    ],
)
def test_passes_when_normalized_monthly_salary_meets_the_minimum(salary_range, expected_monthly):
    assert _passes(salary_range, min_salary=expected_monthly) is True
    assert _passes(salary_range, min_salary=expected_monthly + 1) is False


def test_fails_when_salary_range_is_missing():
    assert _passes(None, min_salary=1000) is False


def test_fails_when_salary_range_is_empty():
    assert _passes("", min_salary=1000) is False


def test_fails_when_salary_range_is_unparseable():
    assert _passes("Competitive salary", min_salary=1000) is False
