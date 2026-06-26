import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.application.ports import ModelUsage
from app.config import DATABASE_URL
from app.infrastructure.orm_models import Base, ModelUsageRow
from app.infrastructure.postgres_model_usage_repository import PostgresModelUsageRepository
from app.infrastructure.postgres_user_repository import PostgresUserRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(), reason="database is not reachable"
)

_USER_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


def _seed_user(conn, user_id: str) -> None:
    conn.execute(
        text(
            "INSERT INTO users (id, email, password_hash, token_version, created_at) "
            "VALUES (:id, :email, 'x', 0, now())"
        ),
        {"id": user_id, "email": f"{user_id}@example.test"},
    )


@pytest.fixture(autouse=True)
def clean_schema():
    engine = create_engine(DATABASE_URL)
    PostgresUserRepository(DATABASE_URL)  # ensure the FK target (users) table exists
    # Ensure the table exists WITHOUT dropping it (dropping would wipe every user's usage).
    # Cleanup is scoped to this suite's fixed test users below; deleting them cascades to
    # their model_usage rows, so no other user's data is ever touched.
    Base.metadata.create_all(engine, tables=[ModelUsageRow.__table__])
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": _USER_ID, "b": _OTHER_USER_ID}
        )
        _seed_user(conn, _USER_ID)
        _seed_user(conn, _OTHER_USER_ID)
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": _USER_ID, "b": _OTHER_USER_ID}
        )


def _usage(user_id: str, model: str, input_tokens: int, output_tokens: int) -> ModelUsage:
    return ModelUsage(
        label="scoring",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        company="Google",
        user_id=user_id,
    )


def test_save_persists_usage_record():
    repo = PostgresModelUsageRepository(DATABASE_URL)

    repo.save(_usage(_USER_ID, "gemini-2.0-flash", 100, 50))
    summary = repo.get_summary(_USER_ID)

    assert len(summary) == 1
    assert summary[0].company == "Google"
    assert summary[0].model == "gemini-2.0-flash"
    assert summary[0].input_tokens == 100
    assert summary[0].output_tokens == 50


def test_get_summary_aggregates_tokens_per_model():
    repo = PostgresModelUsageRepository(DATABASE_URL)
    repo.save(_usage(_USER_ID, "gemini-2.0-flash", 100, 50))
    repo.save(_usage(_USER_ID, "gemini-2.0-flash", 200, 80))

    summary = repo.get_summary(_USER_ID)

    assert len(summary) == 1
    assert summary[0].input_tokens == 300
    assert summary[0].output_tokens == 130


def test_get_summary_returns_separate_rows_per_model():
    repo = PostgresModelUsageRepository(DATABASE_URL)
    repo.save(_usage(_USER_ID, "gemini-2.0-flash", 100, 50))
    repo.save(_usage(_USER_ID, "gemini-2.5-flash", 200, 80))

    summary = repo.get_summary(_USER_ID)

    models = {s.model for s in summary}
    assert models == {"gemini-2.0-flash", "gemini-2.5-flash"}


def test_get_summary_is_isolated_per_user():
    repo = PostgresModelUsageRepository(DATABASE_URL)
    repo.save(_usage(_USER_ID, "gemini-2.0-flash", 100, 50))
    repo.save(_usage(_OTHER_USER_ID, "gemini-2.0-flash", 999, 999))

    summary = repo.get_summary(_USER_ID)

    assert len(summary) == 1
    assert summary[0].input_tokens == 100


def test_get_summary_returns_empty_when_no_records():
    repo = PostgresModelUsageRepository(DATABASE_URL)

    assert repo.get_summary(_USER_ID) == []
