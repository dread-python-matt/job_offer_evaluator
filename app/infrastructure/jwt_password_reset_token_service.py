from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt

from app.application.ports import PasswordResetTokenService, ResetTokenClaims
from app.domain.errors import InvalidPasswordResetTokenError

_ALGORITHM = "HS256"
# Distinguishes reset tokens from session and email-confirmation tokens so none can be
# substituted for another, even when signed with the same secret.
_PURPOSE = "password_reset"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JwtPasswordResetTokenService(PasswordResetTokenService):
    """Single-purpose password-reset tokens as signed JWTs. Claims: `sub` (user id),
    `purpose` (fixed marker), and `ver` (the user's token_version at issue time). Short-lived
    by default; expiry is enforced by `exp`. Stateless — no storage — yet single-use: a
    completed reset bumps the user's token_version, so the embedded `ver` no longer matches
    and the link is rejected even within its TTL."""

    def __init__(
        self,
        secret: str,
        ttl: timedelta = timedelta(hours=1),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._secret = secret
        self._ttl = ttl
        self._clock = clock

    def issue(self, user_id: str, token_version: int) -> str:
        now = self._clock()
        payload = {
            "sub": user_id,
            "ver": token_version,
            "purpose": _PURPOSE,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> ResetTokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidPasswordResetTokenError("invalid reset token") from exc
        if payload.get("purpose") != _PURPOSE or "sub" not in payload or "ver" not in payload:
            raise InvalidPasswordResetTokenError("reset token has the wrong purpose")
        return ResetTokenClaims(user_id=payload["sub"], token_version=payload["ver"])
