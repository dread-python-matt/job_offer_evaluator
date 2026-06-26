from app.infrastructure.db import build_engine, resolve_engine

# A well-formed URL the engine is never asked to connect to — create_engine is lazy, so
# the pool is configured without a reachable database.
_URL = "postgresql+psycopg://u:p@localhost:5432/db"


def test_build_engine_applies_configured_pool_size_and_overflow():
    engine = build_engine(_URL, pool_size=7, max_overflow=3)

    assert engine.pool.size() == 7
    assert engine.pool._max_overflow == 3


def test_build_engine_pool_defaults_match_sqlalchemy_defaults():
    engine = build_engine(_URL)

    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 10


def test_build_engine_keeps_pre_ping_enabled():
    # Liveness check on checkout recycles stale connections; must survive the signature change.
    assert build_engine(_URL).pool._pre_ping is True


def test_resolve_engine_passes_through_an_existing_engine():
    engine = build_engine(_URL)

    assert resolve_engine(engine) is engine
