from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.application.ports import ApiKeyRecord
from app.infrastructure.orm_models import Base, UserApiKeyRow
from app.infrastructure.postgres_api_key_repository import PostgresApiKeyRepository
from app.infrastructure.postgres_user_repository import PostgresUserRepository
from app.config import DATABASE_URL


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="database is not reachable")

# Distinct from the IDs the other integration suites use, so this suite's user
# setup/teardown can never contaminate their shared rows under random test ordering.
_USER_ID = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"
_OTHER_USER_ID = "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2"


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
    # Ensure the table exists WITHOUT dropping it (dropping would wipe every user's API keys).
    # Cleanup is scoped to this suite's fixed test users below; deleting them cascades to
    # their user_api_key rows, so no other user's data is ever touched.
    Base.metadata.create_all(engine, tables=[UserApiKeyRow.__table__])
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


def _record(user_id: str, provider: str, *, limit: float = 5.0) -> ApiKeyRecord:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return ApiKeyRecord(
        user_id=user_id,
        api_provider=provider,
        key_ciphertext=f"cipher-{provider}",
        key_hint="sk-…1234",
        limit_usd=limit,
        tracking_since=now,
        created_at=now,
    )


def test_get_returns_none_when_no_key_stored():
    assert PostgresApiKeyRepository(DATABASE_URL).get(_USER_ID, "openai") is None


def test_add_then_get_returns_the_record():
    repo = PostgresApiKeyRepository(DATABASE_URL)

    repo.add(_record(_USER_ID, "openai", limit=12.5))

    stored = repo.get(_USER_ID, "openai")
    assert stored is not None
    assert stored.api_provider == "openai"
    assert stored.key_ciphertext == "cipher-openai"
    assert stored.key_hint == "sk-…1234"
    assert stored.limit_usd == 12.5


def test_list_for_user_returns_only_that_users_keys():
    repo = PostgresApiKeyRepository(DATABASE_URL)
    repo.add(_record(_USER_ID, "openai"))
    repo.add(_record(_USER_ID, "google"))
    repo.add(_record(_OTHER_USER_ID, "openai"))

    providers = {r.api_provider for r in repo.list_for_user(_USER_ID)}

    assert providers == {"openai", "google"}


def test_add_rejects_a_second_key_for_the_same_provider():
    repo = PostgresApiKeyRepository(DATABASE_URL)
    repo.add(_record(_USER_ID, "openai"))

    with pytest.raises(IntegrityError):
        repo.add(_record(_USER_ID, "openai"))


def test_delete_removes_the_key_and_reports_success():
    repo = PostgresApiKeyRepository(DATABASE_URL)
    repo.add(_record(_USER_ID, "openai"))

    assert repo.delete(_USER_ID, "openai") is True
    assert repo.get(_USER_ID, "openai") is None


def test_delete_returns_false_when_nothing_to_delete():
    assert PostgresApiKeyRepository(DATABASE_URL).delete(_USER_ID, "openai") is False


def test_update_budget_changes_only_the_limit():
    repo = PostgresApiKeyRepository(DATABASE_URL)
    repo.add(_record(_USER_ID, "openai", limit=5.0))

    assert repo.update_budget(_USER_ID, "openai", 20.0) is True

    stored = repo.get(_USER_ID, "openai")
    assert stored.limit_usd == 20.0
    assert stored.key_ciphertext == "cipher-openai"  # key untouched


def test_update_budget_returns_false_for_a_missing_key():
    assert PostgresApiKeyRepository(DATABASE_URL).update_budget(_USER_ID, "openai", 9.0) is False
