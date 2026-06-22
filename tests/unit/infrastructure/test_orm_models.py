from datetime import datetime, timezone

from app.domain.entities import Offer, Salary
from app.infrastructure.orm_models import OfferRow, SalaryRow


def _row(salaries: list[SalaryRow] | None = None, **overrides) -> OfferRow:
    defaults = dict(
        link="https://example.com/offer",
        id="abc123",
        title="Backend Developer",
        company="Acme",
        tech_stack=["Python", "FastAPI"],
        description="desc",
        requirements="reqs",
        benefits="benefits",
        locations=["Warsaw"],
        published_date="2026-06-01",
        scraped_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        portal="pracujpl",
        tech_stack_nice_to_have=["Docker"],
        requirements_nice_to_have="",
        responsibilities="",
        expires="2026-08-01",
        levels=["mid"],
        expired=False,
    )
    defaults.update(overrides)
    row = OfferRow(**defaults)
    row.salaries = salaries or []
    return row


def _salary_row(**overrides) -> SalaryRow:
    defaults = dict(
        id=1,
        offer_id="abc123",
        contract_type="permanent",
        min=10000,
        max=15000,
        currency="PLN",
        period="month",
    )
    defaults.update(overrides)
    return SalaryRow(**defaults)


def test_offer_row_converts_to_domain_offer():
    row = _row()

    offer = row.to_offer()

    assert offer == Offer(
        link="https://example.com/offer",
        title="Backend Developer",
        company="Acme",
        tech_stack=["Python", "FastAPI"],
        tech_stack_nice_to_have=["Docker"],
        description="desc",
        locations=["Warsaw"],
        salaries=[],
        expired=False,
        expires="2026-08-01",
        levels=["mid"],
        published="2026-06-01",
    )


def test_offer_row_defaults_missing_tech_stack_lists_to_empty():
    row = _row(tech_stack=None, tech_stack_nice_to_have=None)

    offer = row.to_offer()

    assert offer.tech_stack == []
    assert offer.tech_stack_nice_to_have == []


def test_offer_row_defaults_missing_locations_to_empty():
    row = _row(locations=None)

    offer = row.to_offer()

    assert offer.locations == []


def test_offer_row_defaults_missing_levels_to_empty():
    row = _row(levels=None)

    offer = row.to_offer()

    assert offer.levels == []


def test_offer_row_defaults_missing_published_date_to_none():
    row = _row(published_date="")

    offer = row.to_offer()

    assert offer.published is None


def test_offer_row_passes_through_expired_flag():
    row = _row(expired=True)

    offer = row.to_offer()

    assert offer.expired is True


def test_offer_row_converts_related_salary_rows():
    row = _row(salaries=[_salary_row(contract_type="b2b", min=10000, max=15000, period="month")])

    offer = row.to_offer()

    assert offer.salaries == [
        Salary(contract_type="b2b", min_amount=10000.0, max_amount=15000.0, currency="PLN", period="month")
    ]


def test_offer_row_converts_multiple_salary_rows():
    row = _row(
        salaries=[
            _salary_row(id=1, contract_type="b2b", min=10000, max=15000),
            _salary_row(id=2, contract_type="permanent", min=8000, max=9000),
        ]
    )

    offer = row.to_offer()

    assert [salary.contract_type for salary in offer.salaries] == ["b2b", "permanent"]


def test_salary_row_converts_to_domain_salary_with_null_amounts():
    salary_row = _salary_row(min=None, max=None)

    salary = salary_row.to_salary()

    assert salary.min_amount is None
    assert salary.max_amount is None
