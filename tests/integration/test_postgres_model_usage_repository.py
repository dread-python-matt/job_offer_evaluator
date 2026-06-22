import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.application.ports import ModelUsage
from app.config import DATABASE_URL
from app.infrastructure.postgres_model_usage_repository import PostgresModelUsageRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(), reason="database is not reachable"
)


@pytest.fixture(autouse=True)
def clean_table():
    # Ensure table exists before cleaning
    PostgresModelUsageRepository(DATABASE_URL)
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM model_usage"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM model_usage"))


def test_save_persists_usage_record():
    repo = PostgresModelUsageRepository(DATABASE_URL)
    usage = ModelUsage(label="scoring", input_tokens=100, output_tokens=50, model="gemini-2.0-flash", company="Google")

    repo.save(usage)
    summary = repo.get_summary()

    assert len(summary) == 1
    assert summary[0].company == "Google"
    assert summary[0].model == "gemini-2.0-flash"
    assert summary[0].input_tokens == 100
    assert summary[0].output_tokens == 50


def test_get_summary_aggregates_tokens_per_model():
    repo = PostgresModelUsageRepository(DATABASE_URL)
    repo.save(ModelUsage(label="scoring", input_tokens=100, output_tokens=50, model="gemini-2.0-flash", company="Google"))
    repo.save(ModelUsage(label="scoring", input_tokens=200, output_tokens=80, model="gemini-2.0-flash", company="Google"))

    summary = repo.get_summary()

    assert len(summary) == 1
    assert summary[0].input_tokens == 300
    assert summary[0].output_tokens == 130


def test_get_summary_returns_separate_rows_per_model():
    repo = PostgresModelUsageRepository(DATABASE_URL)
    repo.save(ModelUsage(label="scoring", input_tokens=100, output_tokens=50, model="gemini-2.0-flash", company="Google"))
    repo.save(ModelUsage(label="scoring", input_tokens=200, output_tokens=80, model="gemini-2.5-flash", company="Google"))

    summary = repo.get_summary()

    models = {s.model for s in summary}
    assert models == {"gemini-2.0-flash", "gemini-2.5-flash"}


def test_get_summary_returns_empty_when_no_records():
    repo = PostgresModelUsageRepository(DATABASE_URL)

    summary = repo.get_summary()

    assert summary == []
