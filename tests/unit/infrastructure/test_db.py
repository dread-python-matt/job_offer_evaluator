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


def _captured_connect_args(monkeypatch, **build_kwargs) -> dict:
    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("app.infrastructure.db.create_engine", fake_create_engine)
    build_engine(_URL, **build_kwargs)
    return captured["connect_args"]


def test_build_engine_sets_a_connect_timeout_so_a_down_db_fails_fast(monkeypatch):
    # Without a libpq connect_timeout a down/unreachable DB hangs for the OS TCP timeout
    # (~2 minutes); the bounded timeout surfaces it as a fast, clear error instead.
    assert _captured_connect_args(monkeypatch) == {"connect_timeout": 10}


def test_build_engine_connect_timeout_is_overridable(monkeypatch):
    assert _captured_connect_args(monkeypatch, connect_timeout=3) == {"connect_timeout": 3}


def test_resolve_engine_passes_through_an_existing_engine():
    engine = build_engine(_URL)

    assert resolve_engine(engine) is engine
