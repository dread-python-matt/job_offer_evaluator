import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app.infrastructure.orm_models import Base, SelectedModelRow
from app.infrastructure.postgres_selected_model_repository import PostgresSelectedModelRepository
from app.infrastructure.postgres_user_repository import PostgresUserRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="database is not reachable")

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
    SelectedModelRow.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine, tables=[SelectedModelRow.__table__])
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


def test_get_returns_none_when_user_has_not_selected():
    assert PostgresSelectedModelRepository(DATABASE_URL).get(_USER_ID) is None


def test_set_then_get_returns_the_model():
    repo = PostgresSelectedModelRepository(DATABASE_URL)

    repo.set(_USER_ID, "gpt-4o")

    assert repo.get(_USER_ID) == "gpt-4o"


def test_set_overwrites_the_users_selection():
    repo = PostgresSelectedModelRepository(DATABASE_URL)
    repo.set(_USER_ID, "gpt-4o")

    repo.set(_USER_ID, "gemini-2.0-flash")

    assert repo.get(_USER_ID) == "gemini-2.0-flash"


def test_selection_is_isolated_per_user():
    repo = PostgresSelectedModelRepository(DATABASE_URL)

    repo.set(_USER_ID, "gpt-4o")

    assert repo.get(_OTHER_USER_ID) is None
