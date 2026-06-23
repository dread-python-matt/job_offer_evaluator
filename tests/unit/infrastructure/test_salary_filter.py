import pytest

from app.domain.entities import Offer, Salary, UserProfile
from app.domain.filters import MatchCriteria
from app.infrastructure.offer_filters import SalaryFilter


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _salary(
    min_amount: float | None,
    max_amount: float | None,
    period: str,
    contract_type: str = "permanent",
) -> Salary:
    return Salary(
        contract_type=contract_type,
        min_amount=min_amount,
        max_amount=max_amount,
        currency="PLN",
        period=period,
    )


def _offer(salaries: list[Salary]) -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme", salaries=salaries)


def _passes(salaries: list[Salary], min_salary: float | None) -> bool:
    criteria = MatchCriteria(candidate=_candidate(), min_salary=min_salary)
    return SalaryFilter().passes(_offer(salaries), criteria)


def test_passes_when_no_minimum_salary_is_requested():
    assert _passes([], min_salary=None) is True


# Real samples pulled from the live `salaries` table, with their expected normalized
# monthly value (the upper bound of the range, /hour /day /year converted to monthly).
@pytest.mark.parametrize(
    ("salaries", "expected_monthly"),
    [
        ([_salary(18000, 22500, "month")], 22500),
        ([_salary(120, 140, "hour")], 140 * 168),
        ([_salary(145, 155, "day")], 155 * 21),
        ([_salary(120000, 132000, "year")], 132000 / 12),
        ([_salary(11000, None, "month")], 11000),
        ([_salary(10000, 10000, "month", contract_type="permanent")], 10000),
        # picks the best (highest) of multiple contract-type entries
        (
            [
                _salary(6720, 10080, "month", contract_type="b2b"),
                _salary(6720, 8400, "month", contract_type="zlecenie"),
            ],
            10080,
        ),
    ],
)
def test_passes_when_normalized_monthly_salary_meets_the_minimum(salaries, expected_monthly):
    assert _passes(salaries, min_salary=expected_monthly) is True
    assert _passes(salaries, min_salary=expected_monthly + 1) is False


def test_fails_when_offer_has_no_salary_entries():
    assert _passes([], min_salary=1000) is False


def test_fails_when_salary_amount_is_missing():
    assert _passes([_salary(None, None, "month")], min_salary=1000) is False


def test_fails_when_salary_period_is_unparseable():
    assert _passes([_salary(50000, 60000, "")], min_salary=1000) is False
