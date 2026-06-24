from sqlalchemy import Engine, create_engine


def build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with production-friendly defaults.

    `pool_pre_ping` checks out connections with a liveness probe so stale/dropped
    connections (idle timeouts, DB restarts) are transparently recycled instead of
    surfacing as errors on the next query."""
    return create_engine(database_url, pool_pre_ping=True)


def resolve_engine(database_or_engine: str | Engine) -> Engine:
    """Accept either a database URL or an already-built engine, returning an engine.

    Lets repositories share one pooled engine in production (pass an Engine) while
    keeping the simple `Repo(DATABASE_URL)` form working for tests/standalone use."""
    if isinstance(database_or_engine, Engine):
        return database_or_engine
    return build_engine(database_or_engine)
