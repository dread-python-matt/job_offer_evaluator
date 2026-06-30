from sqlalchemy import Engine, text


class EngineReadinessProbe:
    """Readiness check for the database: opens a connection and runs `SELECT 1`.

    Raises (a SQLAlchemy `OperationalError`/`DBAPIError`) when the database is unreachable
    or the query fails, which the readiness route translates into a 503. Combined with the
    engine's `connect_timeout`, an unreachable database surfaces in seconds rather than
    hanging the probe. Liveness (`/health`) stays dependency-free; this powers `/health/ready`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> None:
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
