from datetime import datetime, timezone

from app.domain.entities import Offer
from app.infrastructure.orm_models import OfferRow


def _row(**overrides) -> OfferRow:
    defaults = dict(
        link="https://example.com/offer",
        title="Backend Developer",
        company="Acme",
        tech_stack=["Python", "FastAPI"],
        description="desc",
        requirements="reqs",
        benefits="benefits",
        locations=["Warsaw"],
        published_date="2026-06-01",
        salary_range=None,
        scraped_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        portal="pracujpl",
        tech_stack_nice_to_have=["Docker"],
        requirements_nice_to_have="",
        responsibilities="",
    )
    defaults.update(overrides)
    return OfferRow(**defaults)


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
        salary_range=None,
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


def test_offer_row_passes_through_salary_range():
    row = _row(salary_range="10000 - 15000 PLN/month")

    offer = row.to_offer()

    assert offer.salary_range == "10000 - 15000 PLN/month"
