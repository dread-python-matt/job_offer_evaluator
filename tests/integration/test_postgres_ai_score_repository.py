import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app.domain.scoring import AiInsight, MatchScore, ScoreComponent
from app.infrastructure.postgres_ai_score_repository import PostgresAiScoreRepository


def _database_reachable() -> bool:
    try:
        create_engine(DATABASE_URL).connect().close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="database is not reachable")


@pytest.fixture(autouse=True)
def clean_table():
    PostgresAiScoreRepository(DATABASE_URL)  # ensure table exists
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ai_score"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ai_score"))


def _score() -> MatchScore:
    insight = AiInsight(rate=4, pros=["p"], cons=["c"], rate_reason="why")
    return MatchScore().with_component(
        ScoreComponent(name="description", value=0.8, weight=1.0, metadata={"ai_insight": insight})
    )


def test_get_returns_none_on_miss():
    repo = PostgresAiScoreRepository(DATABASE_URL)

    assert repo.get("missing") is None


def test_put_then_get_round_trips_the_score_and_insight():
    repo = PostgresAiScoreRepository(DATABASE_URL)
    repo.put("k1", _score())

    restored = repo.get("k1")

    assert restored is not None
    assert restored.overall_score == _score().overall_score
    assert restored.metadata("ai_insight").rate == 4
