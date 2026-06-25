from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt

from app.application.ports import PasswordResetTokenService
from app.domain.errors import InvalidPasswordResetTokenError

_ALGORITHM = "HS256"
# Distinguishes reset tokens from session and email-confirmation tokens so none can be
# substituted for another, even when signed with the same secret.
_PURPOSE = "password_reset"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JwtPasswordResetTokenService(PasswordResetTokenService):
    """Single-purpose password-reset tokens as signed JWTs. Claims: `sub` (user id) and
    `purpose` (fixed marker). Short-lived by default; expiry is enforced by `exp`. Stateless
    — no storage — so a reset link works exactly once in practice because the first use bumps
    the user's token_version (sessions) and the link normally expires quickly."""

    def __init__(
        self,
        secret: str,
        ttl: timedelta = timedelta(hours=1),
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
            raise InvalidPasswordResetTokenError("invalid reset token") from exc
        if payload.get("purpose") != _PURPOSE or "sub" not in payload:
            raise InvalidPasswordResetTokenError("reset token has the wrong purpose")
        return payload["sub"]
