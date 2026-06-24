import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app.domain.entities import Project, Skill, UserProfile
from app.infrastructure.postgres_user_profile_repository import PostgresUserProfileRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="database is not reachable")


@pytest.fixture(autouse=True)
def clean_table():
    PostgresUserProfileRepository(DATABASE_URL)  # ensure table exists
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM user_profile"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM user_profile"))


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


def test_load_returns_none_when_no_profile_saved():
    repo = PostgresUserProfileRepository(DATABASE_URL)

    assert repo.load() is None


def test_save_then_load_round_trips_the_profile():
    repo = PostgresUserProfileRepository(DATABASE_URL)
    profile = _profile()

    repo.save(profile)

    assert repo.load() == profile


def test_save_overwrites_the_single_profile_row():
    repo = PostgresUserProfileRepository(DATABASE_URL)
    repo.save(_profile())

    updated = UserProfile(summary="Updated", skills=[], projects=[], experience=[])
    repo.save(updated)

    assert repo.load() == updated
