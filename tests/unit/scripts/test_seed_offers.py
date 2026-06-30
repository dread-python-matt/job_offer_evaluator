"""The demo-offer fixture used to let a recruiter see the app working on an empty DB.

These tests cover the *pure* data builder only (no database): they assert the fixture is
large and diverse enough to exercise browsing, filtering, deterministic matching and the
salary calculator. The DB-insertion path (`seed_database`) is thin I/O over this data and is
exercised manually / against a disposable DB, like the other Postgres adapters.
"""

from app.domain.salary_calculator import contract_type_from_label
from app.scripts.seed_offers import (
    SeedOffer,
    SeedSalary,
    build_sample_offers,
    normalized_net,
)

LEVELS = {"Intern", "Junior", "Mid", "Senior", "Lead", "Expert"}
CONTRACTS = {"b2b", "permanent", "zlecenie"}


def test_provides_at_least_fifty_active_offers():
    offers = build_sample_offers()

    active = [o for o in offers if not o.expired]
    # The browser hides expired offers by default, so there must be >= 50 *active* ones for
    # the "most recent offers" view to be full out of the box.
    assert len(active) >= 50


def test_includes_some_expired_offers_to_exercise_the_filter():
    offers = build_sample_offers()

    expired = [o for o in offers if o.expired]
    assert 0 < len(expired) < len(offers)


def test_covers_every_seniority_level():
    offers = build_sample_offers()

    seen = {level for offer in offers for level in offer.levels}
    assert seen == LEVELS


def test_covers_every_contract_type():
    offers = build_sample_offers()

    seen = {salary.contract_type for offer in offers for salary in offer.salaries}
    assert CONTRACTS <= seen
    # Every contract label must be one the net calculator understands, so normalized_salary
    # rows can be computed for the demo data.
    assert all(contract_type_from_label(label) is not None for label in seen)


def test_offers_span_many_portals():
    offers = build_sample_offers()

    assert len({offer.portal for offer in offers}) >= 6


def test_tech_stacks_are_diverse():
    offers = build_sample_offers()

    techs = {
        tech.lower()
        for offer in offers
        for tech in (*offer.tech_stack, *offer.tech_stack_nice_to_have)
    }
    assert len(techs) >= 25


def test_offers_come_from_many_companies():
    offers = build_sample_offers()

    assert len({offer.company for offer in offers}) >= 10


def test_every_offer_has_at_least_one_well_formed_salary():
    offers = build_sample_offers()

    for offer in offers:
        assert offer.salaries
        for salary in offer.salaries:
            assert 0 < salary.min_amount <= salary.max_amount


def test_active_offers_are_recent():
    offers = build_sample_offers()

    recent_days = max(o.published_days_ago for o in offers if not o.expired)
    assert recent_days <= 30


def test_normalized_net_is_positive_and_below_gross():
    salary = SeedSalary(contract_type="b2b", min_amount=12_000.0, max_amount=20_000.0)

    net = normalized_net(salary)

    assert net is not None
    net_min, net_max, midpoint = net
    assert 0 < net_min <= midpoint <= net_max
    # Net take-home is always below the gross it was derived from.
    assert net_max < salary.max_amount


def test_unknown_contract_label_has_no_normalized_net():
    assert normalized_net(SeedSalary("internship-stipend", 3_000.0, 4_000.0)) is None


def test_seed_offer_and_salary_are_simple_value_objects():
    # The builder returns plain, framework-free value objects (no ORM/SQLAlchemy), so the
    # data can be built and asserted on without a database.
    offer = build_sample_offers()[0]
    assert isinstance(offer, SeedOffer)
    assert all(isinstance(s, SeedSalary) for s in offer.salaries)
