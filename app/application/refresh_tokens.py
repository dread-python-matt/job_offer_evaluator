import hashlib
import secrets
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class InvalidRefreshTokenError(Exception):
    """A presented refresh token is unknown, expired, or already consumed. When reuse of an
    already-consumed token is detected the whole token family is revoked before this is
    raised — callers should clear the session and force re-authentication."""


@dataclass(frozen=True)
class RefreshTokenRecord:
    """A single issued refresh token. Only the SHA-256 `token_hash` is stored, never the raw
    token. `family_id` groups a rotation chain so a detected reuse can revoke all of it."""

    id: str
    user_id: str
    family_id: str
    token_hash: str
    expires_at: datetime
    consumed_at: datetime | None = None


class RefreshTokenRepository(ABC):
    @abstractmethod
    def add(self, record: RefreshTokenRecord) -> None: ...

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None: ...

    @abstractmethod
    def mark_consumed(self, token_id: str, consumed_at: datetime) -> None: ...

    @abstractmethod
    def revoke_family(self, family_id: str) -> None:
        """Invalidate every token sharing `family_id` (the whole rotation chain)."""

    @abstractmethod
    def revoke_user(self, user_id: str) -> None:
        """Invalidate every refresh token for a user (logout-everywhere / password change)."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RefreshTokenService:
    """Issues and rotates opaque refresh tokens with reuse detection (RFC 9700 / OWASP).

    Each rotation consumes the presented token and issues a successor in the same family.
    Presenting an already-consumed token is treated as theft: the entire family is revoked
    and the rotation is rejected. Tokens are persisted only as SHA-256 hashes, so a database
    leak does not expose usable tokens.
    """

    def __init__(
        self,
        repository: RefreshTokenRepository,
        ttl: timedelta,
        clock: Callable[[], datetime] = _utc_now,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._repository = repository
        self._ttl = ttl
        self._clock = clock
        self._token_factory = token_factory
        self._id_factory = id_factory

    def issue(self, user_id: str, family_id: str | None = None) -> str:
        """Issue a new refresh token for the user, returning the raw token (the only time it
        exists in plaintext). Starts a new family unless one is supplied (rotation)."""
        raw = self._token_factory()
        self._repository.add(
            RefreshTokenRecord(
                id=self._id_factory(),
                user_id=user_id,
                family_id=family_id or self._id_factory(),
                token_hash=_hash_token(raw),
                expires_at=self._clock() + self._ttl,
            )
        )
        return raw

    def rotate(self, raw_token: str) -> tuple[str, str]:
        """Validate and rotate a refresh token, returning (user_id, new_raw_token). Raises
        InvalidRefreshTokenError if the token is unknown, expired, or being reused."""
        record = self._repository.get_by_hash(_hash_token(raw_token))
        if record is None:
            raise InvalidRefreshTokenError("unknown refresh token")
        if record.consumed_at is not None:
            # An already-rotated token is being replayed: treat as theft and burn the family.
            self._repository.revoke_family(record.family_id)
            raise InvalidRefreshTokenError("refresh token reuse detected")
        if self._clock() >= record.expires_at:
            raise InvalidRefreshTokenError("expired refresh token")
        self._repository.mark_consumed(record.id, self._clock())
        return record.user_id, self.issue(record.user_id, family_id=record.family_id)

    def revoke(self, raw_token: str) -> None:
        """Revoke the family of a refresh token (e.g. on logout). Unknown tokens are ignored."""
        record = self._repository.get_by_hash(_hash_token(raw_token))
        if record is not None:
            self._repository.revoke_family(record.family_id)

    def revoke_user(self, user_id: str) -> None:
        self._repository.revoke_user(user_id)
