import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app.infrastructure.postgres_selected_model_repository import PostgresSelectedModelRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="database is not reachable")


@pytest.fixture(autouse=True)
def clean_table():
    PostgresSelectedModelRepository(DATABASE_URL)  # ensure table exists
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM selected_model"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM selected_model"))


def test_get_returns_none_when_nothing_selected():
    assert PostgresSelectedModelRepository(DATABASE_URL).get() is None


def test_set_then_get_returns_the_model():
    repo = PostgresSelectedModelRepository(DATABASE_URL)

    repo.set("gpt-4o")

    assert repo.get() == "gpt-4o"


def test_set_overwrites_the_single_row():
    repo = PostgresSelectedModelRepository(DATABASE_URL)
    repo.set("gpt-4o")

    repo.set("gemini-2.0-flash")

    assert repo.get() == "gemini-2.0-flash"
