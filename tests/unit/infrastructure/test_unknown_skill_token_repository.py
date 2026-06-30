"""PostgresUnknownSkillTokenRepository on an in-memory SQLite engine: snapshot-replace semantics
(a rebuild swaps the whole tail, never accumulates across runs) and frequency-ordered reads."""

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.application.ports import UnknownSkillToken
from app.infrastructure.orm_models import Base, UnknownSkillTokenRow
from app.infrastructure.postgres_unknown_skill_token_repository import (
    PostgresUnknownSkillTokenRepository,
)


def _repo() -> PostgresUnknownSkillTokenRepository:
    # StaticPool keeps one shared in-memory connection so writes persist across sessions.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[UnknownSkillTokenRow.__table__])
    return PostgresUnknownSkillTokenRepository(engine)


def test_replace_all_then_top_orders_by_frequency_and_keeps_samples():
    repo = _repo()
    repo.replace_all(
        [
            UnknownSkillToken("cobolx", 4, ["CobolX", "cobolx"]),
            UnknownSkillToken("whitespace", 5, ["Whitespace"]),
        ]
    )

    top = repo.top()

    assert [(t.normalized, t.occurrences) for t in top] == [
        ("whitespace", 5),
        ("cobolx", 4),
    ]
    assert top[1].raw_samples == ["CobolX", "cobolx"]


def test_replace_all_is_a_snapshot_not_cumulative():
    repo = _repo()
    repo.replace_all([UnknownSkillToken("a", 3, [])])
    repo.replace_all([UnknownSkillToken("b", 1, [])])

    # The second snapshot replaces the first — "a" is gone, counts aren't summed across runs.
    assert [t.normalized for t in repo.top()] == ["b"]


def test_top_respects_the_limit():
    repo = _repo()
    repo.replace_all(
        [
            UnknownSkillToken("a", 3, []),
            UnknownSkillToken("b", 2, []),
            UnknownSkillToken("c", 1, []),
        ]
    )

    assert [t.normalized for t in repo.top(2)] == ["a", "b"]
