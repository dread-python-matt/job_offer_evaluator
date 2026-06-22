import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.domain.entities import Offer
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
