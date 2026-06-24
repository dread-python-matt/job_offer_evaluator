import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.domain.entities import Offer
from app.domain.filters import OfferBrowseFilters
from app.config import DATABASE_URL
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(), reason="offers_postgres database is not reachable"
)


def test_list_offers_returns_offers_from_real_read_only_database():
    repository = PostgresOfferRepository(DATABASE_URL)

    offers = repository.list_offers()

    assert len(offers) > 0
    assert all(isinstance(offer, Offer) for offer in offers)
    sample = offers[0]
    assert sample.link
    assert sample.title
    assert sample.company
    assert isinstance(sample.tech_stack, list)
    assert isinstance(sample.tech_stack_nice_to_have, list)


def test_count_offers_matches_number_of_listed_offers():
    repository = PostgresOfferRepository(DATABASE_URL)

    assert repository.count_offers() == len(repository.list_offers())


def test_list_offers_returns_offers_sorted_by_published_date_newest_first():
    repository = PostgresOfferRepository(DATABASE_URL)

    offers = repository.list_offers()

    dates = [o.published for o in offers if o.published]
    assert dates == sorted(dates, reverse=True)


def _best_net_by_link(column: str) -> dict[str, float]:
    """Per offer link, the max of the given normalized net column — the representative
    the repository sorts/filters on for that bound."""
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT o.link, MAX(ns.{column}) AS amount "
                "FROM offers o "
                "JOIN salaries s ON s.offer_id = o.id "
                "JOIN normalized_salary ns ON ns.salary_id = s.id "
                "GROUP BY o.link"
            )
        ).fetchall()
    return {link: float(amount) for link, amount in rows}


def test_browse_sorts_by_salary_max_descending_via_normalized_table():
    repository = PostgresOfferRepository(DATABASE_URL)
    best = _best_net_by_link("net_of_max")

    offers, _ = repository.browse_offers(
        OfferBrowseFilters(sort_by="salary_max", sort_order="desc"), limit=30, offset=0
    )

    amounts = [best[o.link] for o in offers if o.link in best]
    assert amounts, "expected offers with normalized salary data"
    assert amounts == sorted(amounts, reverse=True)


def test_browse_sorts_by_salary_min_ascending_via_normalized_table():
    repository = PostgresOfferRepository(DATABASE_URL)
    best = _best_net_by_link("net_of_min")

    offers, _ = repository.browse_offers(
        OfferBrowseFilters(sort_by="salary_min", sort_order="asc"), limit=30, offset=0
    )

    amounts = [best[o.link] for o in offers if o.link in best]
    assert amounts == sorted(amounts)


def test_browse_filters_by_min_salary_on_the_net_floor():
    repository = PostgresOfferRepository(DATABASE_URL)
    net_floor = _best_net_by_link("net_of_min")  # the filter uses net_of_min
    threshold = 15000.0

    offers, total = repository.browse_offers(
        OfferBrowseFilters(min_salary=threshold), limit=100, offset=0
    )

    assert total >= len(offers)
    for offer in offers:
        assert net_floor.get(offer.link, 0.0) >= threshold


def test_browse_min_salary_is_a_subset_of_unfiltered():
    repository = PostgresOfferRepository(DATABASE_URL)

    base_total = repository.browse_offers(OfferBrowseFilters(), limit=1, offset=0)[1]
    filtered_total = repository.browse_offers(
        OfferBrowseFilters(min_salary=25000.0), limit=1, offset=0
    )[1]

    assert filtered_total <= base_total
