from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt

from app.application.ports import TokenClaims, TokenService
from app.domain.errors import AuthenticationError

_ALGORITHM = "HS256"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JwtTokenService(TokenService):
    """Stateless session tokens as signed JWTs. Claims: `sub` (user id) and `ver`
    (the user's token_version, so revocation is enforced by the caller comparing it to
    the live user). Expiry is enforced by the `exp` claim."""

    def __init__(
        self,
        secret: str,
        ttl: timedelta = timedelta(days=7),
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
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
            return TokenClaims(user_id=payload["sub"], token_version=payload["ver"])
        except (jwt.PyJWTError, KeyError) as exc:
            raise AuthenticationError("invalid session token") from exc
