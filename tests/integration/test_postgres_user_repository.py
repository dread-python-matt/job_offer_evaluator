from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app.domain.auth import User
from app.infrastructure.postgres_user_repository import PostgresUserRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="database is not reachable")

_USER_ID = "33333333-3333-3333-3333-333333333333"


def _user(email_verified: bool) -> User:
    return User(
        id=_USER_ID,
        email=f"{_USER_ID}@example.test",
        password_hash="hashed",
        token_version=0,
        created_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        email_verified=email_verified,
    )


@pytest.fixture(autouse=True)
def clean_users():
    PostgresUserRepository(DATABASE_URL)  # ensure the users table exists
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER_ID})
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER_ID})


def test_add_then_get_round_trips_an_unverified_user():
    repo = PostgresUserRepository(DATABASE_URL)

    repo.add(_user(email_verified=False))

    assert repo.get_by_id(_USER_ID).email_verified is False
    assert repo.get_by_email(f"{_USER_ID}@example.test").email_verified is False


def test_add_then_get_round_trips_a_verified_user():
    repo = PostgresUserRepository(DATABASE_URL)

    repo.add(_user(email_verified=True))

    assert repo.get_by_id(_USER_ID).email_verified is True


def test_mark_email_verified_flips_the_flag():
    repo = PostgresUserRepository(DATABASE_URL)
    repo.add(_user(email_verified=False))

    repo.mark_email_verified(_USER_ID)

    assert repo.get_by_id(_USER_ID).email_verified is True


def test_mark_email_verified_is_idempotent():
    repo = PostgresUserRepository(DATABASE_URL)
    repo.add(_user(email_verified=True))

    repo.mark_email_verified(_USER_ID)

    assert repo.get_by_id(_USER_ID).email_verified is True
