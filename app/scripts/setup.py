"""One-command project setup: bring a fresh database to a runnable demo state.

Collapses the repetitive local setup — a pre-flight database check, `alembic upgrade head`, and
seeding the demo offers — into a single idempotent command, matching the "setup" role in
GitHub's *Scripts to Rule Them All* pattern. Dependencies themselves are handled by `uv sync` /
`uv run` (and baked into the Docker image), so this script owns only the project's initial
*state*, not its dependencies.

The demo login is created ONLY when `--demo` is passed — never silently bundled with the offers
seed. It's a well-known-password account, so creating it stays a deliberate, explicit choice
(the same reason `seed_offers` and `seed_user` are kept as separate scripts).

Every step is idempotent, so this is safe to re-run at any time.

Usage:
    uv run python -m app.scripts.setup            # migrate + seed demo offers
    uv run python -m app.scripts.setup --demo     # ...plus the demo login (demo@example.com / Demo1234!)
    docker compose run --rm setup                 # same, in Docker
    docker compose run --rm setup --demo          # ...plus the demo login, in Docker
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SetupOutcome:
    """What a setup run did. `demo_user_created` is None when the demo login wasn't requested
    (no `--demo`), True when it was created, and False when it already existed."""

    offers_seeded: int
    demo_user_created: bool | None


def run_setup(
    *,
    ensure_database_ready: Callable[[], None],
    migrate: Callable[[], None],
    seed_offers: Callable[[], int],
    seed_demo_user: Callable[[], bool] | None,
) -> SetupOutcome:
    """Run the idempotent setup steps in order: confirm the database is reachable, apply
    migrations, seed the demo offers, and — only when `seed_demo_user` is provided (i.e. the
    caller passed `--demo`) — create the demo login. Pure orchestration over injected steps, so
    it is unit-testable without real I/O; `main` wires the concrete steps. A failing readiness
    check aborts before any migration or write happens."""
    ensure_database_ready()
    migrate()
    offers_seeded = seed_offers()
    demo_user_created = seed_demo_user() if seed_demo_user is not None else None
    return SetupOutcome(offers_seeded=offers_seeded, demo_user_created=demo_user_created)


def _run_migrations() -> None:
    """Apply Alembic migrations up to head (idempotent — already-applied revisions are skipped).

    Uses Alembic's Python command API rather than a subprocess, so it behaves identically on
    every OS and inside the container, and resolves the config/scripts from the repo root so it
    doesn't depend on the current working directory. The database URL is supplied by
    `alembic/env.py`, which reads `app.config.DATABASE_URL`."""
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "alembic"))
    command.upgrade(config, "head")


def _print_summary(outcome: SetupOutcome) -> None:
    print("\nSetup complete:")
    print("  - migrations applied (up to head)")
    print(f"  - seeded {outcome.offers_seeded} demo offers")
    if outcome.demo_user_created is None:
        print("  - demo login: skipped (pass --demo to create demo@example.com / Demo1234!)")
    elif outcome.demo_user_created:
        print("  - demo login: created demo@example.com / Demo1234!")
    else:
        print("  - demo login: already existed (left unchanged)")
    print(
        "\nNext: run the API with `uv run python main.py`, start the frontend with "
        "`npm --prefix frontend start`, and sign in."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command setup: check the database, apply migrations, and seed demo data."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Also create the demo login (demo@example.com / Demo1234!). Off by default.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # Imported here (not at module top) so `run_setup` can be imported and unit-tested without a
    # configured DATABASE_URL — matching app.scripts.seed_offers / seed_user.
    from sqlalchemy.exc import SQLAlchemyError

    from app.config import DATABASE_URL
    from app.infrastructure.argon2_password_hasher import Argon2PasswordHasher
    from app.infrastructure.db import build_engine
    from app.infrastructure.db_readiness import EngineReadinessProbe
    from app.infrastructure.postgres_user_repository import PostgresUserRepository
    from app.scripts import seed_offers as seed_offers_module
    from app.scripts.seed_user import seed_user as seed_user_fn

    engine = build_engine(DATABASE_URL)

    def ensure_database_ready() -> None:
        try:
            EngineReadinessProbe(engine).check()
        except SQLAlchemyError as exc:
            # Fail fast with an actionable message instead of a raw driver traceback (the engine's
            # connect_timeout returns in seconds). The URL is never printed — it carries the password.
            raise SystemExit(
                "Setup aborted: the database is not reachable.\n"
                "  Start Postgres and re-run this command, e.g.:\n"
                "    docker compose up -d db\n"
                f"  (connection error: {type(exc).__name__})"
            ) from exc

    def seed_offers_step() -> int:
        offers = seed_offers_module.build_sample_offers()
        return seed_offers_module.seed_database(engine, offers).offers

    def seed_demo_user_step() -> bool:
        return seed_user_fn(PostgresUserRepository(DATABASE_URL), Argon2PasswordHasher()).created

    outcome = run_setup(
        ensure_database_ready=ensure_database_ready,
        migrate=_run_migrations,
        seed_offers=seed_offers_step,
        seed_demo_user=seed_demo_user_step if args.demo else None,
    )
    _print_summary(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
