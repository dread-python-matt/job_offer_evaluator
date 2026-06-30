from sqlalchemy import Engine, create_engine


def build_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    connect_timeout: int = 10,
) -> Engine:
    """Create a SQLAlchemy engine with production-friendly defaults.

    `pool_pre_ping` checks out connections with a liveness probe so stale/dropped
    connections (idle timeouts, DB restarts) are transparently recycled instead of
    surfacing as errors on the next query.

    `pool_size` / `max_overflow` size the connection pool (SQLAlchemy's own defaults of
    5 / 10). Raise them for high-concurrency deployments — but keep the total across all
    workers (`WORKERS * (pool_size + max_overflow)`) under the database's connection limit.

    `connect_timeout` (libpq, seconds) bounds how long a single connection attempt waits
    before failing. Without it a down/unreachable database hangs for the OS TCP timeout
    (~2 minutes); with it the process fails fast with a clear `OperationalError` instead."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        connect_args={"connect_timeout": connect_timeout},
    )


def resolve_engine(database_or_engine: str | Engine) -> Engine:
    """Accept either a database URL or an already-built engine, returning an engine.

    Lets repositories share one pooled engine in production (pass an Engine) while
    keeping the simple `Repo(DATABASE_URL)` form working for tests/standalone use."""
    if isinstance(database_or_engine, Engine):
        return database_or_engine
    return build_engine(database_or_engine)
