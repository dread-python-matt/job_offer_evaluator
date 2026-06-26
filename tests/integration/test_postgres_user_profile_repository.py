import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app.domain.entities import Project, Skill, UserProfile
from app.infrastructure.orm_models import Base, UserProfileRow
from app.infrastructure.postgres_user_profile_repository import PostgresUserProfileRepository
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
    # Ensure the table exists WITHOUT dropping it (dropping would wipe every user's profile).
    # Cleanup is scoped to this suite's fixed test users below; deleting them cascades to
    # their profile rows, so no other user's data is ever touched.
    Base.metadata.create_all(engine, tables=[UserProfileRow.__table__])
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


def _profile() -> UserProfile:
    return UserProfile(
        summary="Dev",
        skills=[Skill(name="Python", rating=5)],
        projects=[
            Project(
                name="Evaluator",
                repository_link="",
                summary="Job matcher",
                date_from="2026-01",
                date_to="2026-06",
                tech_stack=["Python"],
            )
        ],
        experience=[],
    )


def test_load_returns_none_when_user_has_no_profile():
    repo = PostgresUserProfileRepository(DATABASE_URL)

    assert repo.load(_USER_ID) is None


def test_save_then_load_round_trips_the_profile():
    repo = PostgresUserProfileRepository(DATABASE_URL)
    profile = _profile()

    repo.save(_USER_ID, profile)

    assert repo.load(_USER_ID) == profile


def test_save_overwrites_the_users_profile():
    repo = PostgresUserProfileRepository(DATABASE_URL)
    repo.save(_USER_ID, _profile())

    updated = UserProfile(summary="Updated", skills=[], projects=[], experience=[])
    repo.save(_USER_ID, updated)

    assert repo.load(_USER_ID) == updated


def test_profiles_are_isolated_per_user():
    repo = PostgresUserProfileRepository(DATABASE_URL)

    repo.save(_USER_ID, _profile())

    assert repo.load(_OTHER_USER_ID) is None
