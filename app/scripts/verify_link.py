"""Dev/admin helper: print a working email-confirmation link for an existing account.

Use when SMTP isn't configured (the app logs links instead of sending them) and you need
to confirm an account that already registered.

This is a LOCAL command-line tool, not an HTTP endpoint. It mints a token with the app's
JWT_SECRET, so it grants nothing that anyone with the project's secret and database
couldn't already do. The printed link contains a live bearer token (valid for
EMAIL_VERIFICATION_TTL_HOURS) and, because /auth/verify-email auto-logs-in, following it
signs you in as that account — so treat the link like a password and don't share it.

Usage:
    uv run python -m app.scripts.verify_link someone@example.com
"""

import sys
from collections.abc import Callable
from datetime import timedelta

from app.application.ports import UserRepository, VerificationTokenService
from app.config import APP_BASE_URL, DATABASE_URL, EMAIL_VERIFICATION_TTL_HOURS, JWT_SECRET
from app.infrastructure.jwt_verification_token_service import JwtVerificationTokenService
from app.infrastructure.postgres_user_repository import PostgresUserRepository


def build_verification_link(
    users: UserRepository,
    tokens: VerificationTokenService,
    link_builder: Callable[[str], str],
    email: str,
) -> str | None:
    """Return a confirmation link for `email`, or None when no such account exists. The
    email is normalized the same way registration stores it (trimmed, lowercased)."""
    user = users.get_by_email(email.strip().lower())
    if user is None:
        return None
    return link_builder(tokens.issue(user.id))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m app.scripts.verify_link <email>", file=sys.stderr)
        return 2
    email = args[0]
    users = PostgresUserRepository(DATABASE_URL)
    tokens = JwtVerificationTokenService(
        JWT_SECRET, ttl=timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS)
    )
    link = build_verification_link(
        users, tokens, lambda token: f"{APP_BASE_URL}/verify-email?token={token}", email
    )
    if link is None:
        print(f"No account found for {email!r}", file=sys.stderr)
        return 1
    print(link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
