from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt

from app.application.ports import VerificationTokenService
from app.domain.errors import InvalidVerificationTokenError

_ALGORITHM = "HS256"
# Distinguishes confirmation tokens from session tokens so the two can never be
# substituted for one another, even when signed with the same secret.
_PURPOSE = "email_verification"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JwtVerificationTokenService(VerificationTokenService):
    """Single-purpose email-confirmation tokens as signed JWTs. Claims: `sub` (user id)
    and `purpose` (fixed marker). Short-lived by default; expiry is enforced by `exp`.
    Stateless — no storage — so following a stale or replayed link simply re-verifies an
    already-verified account (a harmless no-op upstream)."""

    def __init__(
        self,
        secret: str,
        ttl: timedelta = timedelta(hours=24),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._secret = secret
        self._ttl = ttl
        self._clock = clock

    def issue(self, user_id: str) -> str:
        now = self._clock()
        payload = {
            "sub": user_id,
            "purpose": _PURPOSE,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> str:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidVerificationTokenError("invalid verification token") from exc
        if payload.get("purpose") != _PURPOSE or "sub" not in payload:
            raise InvalidVerificationTokenError("verification token has the wrong purpose")
        return payload["sub"]
