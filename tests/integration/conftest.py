"""Safety guard for the integration test suite.

These integration tests run against the database named by `DATABASE_URL` and there is no
separate test database. The fixtures are now scoped (they create/delete only their own fixed
test user IDs and prefixed cache keys — no `DROP`/`TRUNCATE`), but they still *write* to that
database, so they must never be pointed at a real/dev database. (A prior version dropped whole
tables and emptied `user_profile` against the dev DB — this guard plus the scoped fixtures are
the two layers that prevent a recurrence.)

To keep them off a real database by accident, every test under `tests/integration/` is skipped
at collection time (before any fixture runs) unless the target database is clearly a throwaway
test database:

  * its database name contains "test" (e.g. `offers_test`), or
  * `ALLOW_DESTRUCTIVE_DB_TESTS=1` is set to explicitly opt in (e.g. in CI against a
    disposable DB).

Run them safely, for example:
  DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/offers_test uv run pytest tests/integration
"""

import os
from pathlib import Path

import pytest

from app.config import DATABASE_URL

_HERE = Path(__file__).resolve().parent
_TRUTHY = {"1", "true", "yes", "on"}


def _database_name(url: str) -> str:
    """The database name from a SQLAlchemy URL, lowercased (path tail, sans query string)."""
    return url.rsplit("/", 1)[-1].split("?", 1)[0].strip().lower()


def destructive_db_tests_allowed(url: str = DATABASE_URL) -> bool:
    if os.environ.get("ALLOW_DESTRUCTIVE_DB_TESTS", "").strip().lower() in _TRUTHY:
        return True
    return "test" in _database_name(url)


def _under_integration_dir(item: pytest.Item) -> bool:
    return _HERE in Path(str(item.fspath)).resolve().parents


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if destructive_db_tests_allowed():
        return
    skip = pytest.mark.skip(
        reason=(
            f"Refusing to run integration tests against database "
            f"'{_database_name(DATABASE_URL)}' (no 'test' in its name): they write to it. "
            f"Point DATABASE_URL at a disposable test DB or set ALLOW_DESTRUCTIVE_DB_TESTS=1."
        )
    )
    for item in items:
        if _under_integration_dir(item):
            item.add_marker(skip)
