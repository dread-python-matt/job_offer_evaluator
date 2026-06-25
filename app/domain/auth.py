from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    """An authenticated account. `token_version` is embedded in issued session tokens;
    bumping it invalidates every previously issued token for this user (logout-everywhere,
    and automatic invalidation on password change). `email_verified` gates login: a freshly
    registered account is unverified until the emailed confirmation link is followed."""

    id: str
    email: str
    password_hash: str
    token_version: int = 0
    created_at: datetime | None = None
    email_verified: bool = False
