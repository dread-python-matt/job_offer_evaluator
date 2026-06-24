from app.domain.entities import Offer, Salary, UserProfile
from app.domain.filters import MatchCriteria
from app.infrastructure.offer_filters import SalaryFilter


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _salary(
    net_min: float | None = None,
    net_mid: float | None = None,
    net_max: float | None = None,
    contract_type: str = "permanent",
) -> Salary:
    return Salary(
        contract_type=contract_type,
        min_amount=None,
        max_amount=None,
        currency="PLN",
        period="month",
        net_min=net_min,
        net_mid=net_mid,
        net_max=net_max,
    )


def _offer(salaries: list[Salary]) -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme", salaries=salaries)


def _passes(salaries: list[Salary], min_salary: float | None) -> bool:
    criteria = MatchCriteria(candidate=_candidate(), min_salary=min_salary)
    return SalaryFilter().passes(_offer(salaries), criteria)


def test_passes_when_no_minimum_salary_is_requested():
    assert _passes([], min_salary=None) is True


def test_passes_when_the_net_floor_meets_the_minimum():
    salaries = [_salary(net_min=15000, net_mid=18000, net_max=21000)]

    assert _passes(salaries, min_salary=15000) is True
    assert _passes(salaries, min_salary=15000.01) is False


def test_uses_the_best_contract_types_net_floor():
    salaries = [
        _salary(net_min=10000, net_mid=12000, net_max=14000, contract_type="zlecenie"),
        _salary(net_min=16000, net_mid=20000, net_max=24000, contract_type="b2b"),
    ]

    assert _passes(salaries, min_salary=16000) is True  # the b2b floor qualifies
    assert _passes(salaries, min_salary=16000.01) is False


def test_fails_when_offer_has_no_salary_entries():
    assert _passes([], min_salary=1000) is False


def test_fails_when_offer_has_no_normalized_net():
    assert _passes([_salary()], min_salary=1000) is False
