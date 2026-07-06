"""Seed a ready-to-use demo account so you can log in immediately.

Registration is email-confirmed: a normally-registered account can't log in until the emailed
confirmation link is followed, and with no SMTP configured that link is only *logged* to the API
console. For the zero-config demo that's friction, so this script creates a single
**already-verified** account with known credentials — the demo login documented in the README.

It is idempotent: if the account already exists it is left as-is (its password is never
overwritten) and only marked verified if it wasn't, so re-running is safe.

⚠ This creates an account with a well-known password. It is a convenience for local demos —
do not run it against a production database.

Usage:
    uv run python -m app.scripts.seed_user
    uv run python -m app.scripts.seed_user --email you@example.com --password 'S3cret!pass'
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.ports import PasswordHasher, UserRepository
from app.domain.auth import User

# The demo credentials advertised in the README. The password satisfies the app's password
# policy (see app/domain/password_policy.py), so the same account is also creatable through the
# normal register/reset flows — a test guards this.
DEFAULT_DEMO_EMAIL = "demo@example.com"
DEFAULT_DEMO_PASSWORD = "Demo1234!"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SeedUserResult:
    """Outcome of a seed run. `created` is False when the account already existed."""

    user_id: str
    email: str
    created: bool


def seed_user(
    users: UserRepository,
    hasher: PasswordHasher,
    *,
    email: str = DEFAULT_DEMO_EMAIL,
    password: str = DEFAULT_DEMO_PASSWORD,
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    clock: Callable[[], datetime] = _utc_now,
) -> SeedUserResult:
    """Create a verified account for `email`/`password`, or return the existing one unchanged.

    The email is normalized the same way registration stores it (trimmed, lowercased). When an
    account already exists it is never overwritten (its password stays as-is); it is only marked
    verified if it wasn't, so the demo login keeps working. Idempotent by design.
    """
    normalized = email.strip().lower()
    existing = users.get_by_email(normalized)
    if existing is not None:
        if not existing.email_verified:
            users.mark_email_verified(existing.id)
        return SeedUserResult(user_id=existing.id, email=normalized, created=False)

    user = User(
        id=id_factory(),
        email=normalized,
        password_hash=hasher.hash(password),
        token_version=0,
        created_at=clock(),
        email_verified=True,
    )
    users.add(user)
    return SeedUserResult(user_id=user.id, email=normalized, created=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a verified demo account so you can log in without email confirmation."
    )
    parser.add_argument(
        "--email", default=DEFAULT_DEMO_EMAIL, help="Account email (default: %(default)s)."
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_DEMO_PASSWORD,
        help="Account password (default: the demo password).",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # Imported here (not at module top) so the seeding logic can be imported/tested without
    # DATABASE_URL set — matching app.scripts.seed_offers.
    from app.config import DATABASE_URL
    from app.infrastructure.argon2_password_hasher import Argon2PasswordHasher
    from app.infrastructure.postgres_user_repository import PostgresUserRepository

    users = PostgresUserRepository(DATABASE_URL)
    result = seed_user(
        users, Argon2PasswordHasher(), email=args.email, password=args.password
    )

    if result.created:
        print(f"Created verified demo account: {result.email}")
        print(f"  password: {args.password}")
        print("  Log in immediately at the frontend — no email confirmation needed.")
    else:
        print(f"Demo account already exists: {result.email} (left unchanged; ensured verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
