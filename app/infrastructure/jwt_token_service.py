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
            # Verify the signature but NOT expiry here: PyJWT validates `exp` against the real
            # wall clock, which ignores the injected `clock` and makes expiry time-dependent and
            # untestable. Decode the claims, then enforce `exp` against `self._clock` so issue and
            # verify share one clock. In production `clock` is real UTC now, so the expiry
            # guarantee is unchanged.
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                options={"verify_exp": False},
            )
            expires_at = int(payload["exp"])
            claims = TokenClaims(user_id=payload["sub"], token_version=payload["ver"])
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise AuthenticationError("invalid session token") from exc
        if expires_at <= int(self._clock().timestamp()):
            raise AuthenticationError("invalid session token")
        return claims
