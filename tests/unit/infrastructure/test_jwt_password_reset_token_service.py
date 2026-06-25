from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.domain.errors import InvalidPasswordResetTokenError
from app.infrastructure.jwt_password_reset_token_service import JwtPasswordResetTokenService
from app.infrastructure.jwt_verification_token_service import JwtVerificationTokenService

_SECRET = "test-secret-key-at-least-32-bytes-long!"
# Anchored to the real clock: PyJWT validates exp/iat against wall-clock time, so issuing
# with a fixed fake time would make the round-trip flaky (a future iat is rejected). Deriving
# the base from "now" keeps the valid case valid and the expired case reliably in the past.
_NOW = datetime.now(timezone.utc)


def _at(moment: datetime):
    return lambda: moment


def test_issue_then_verify_returns_the_user_id_and_token_version():
    service = JwtPasswordResetTokenService(secret=_SECRET, ttl=timedelta(hours=1), clock=_at(_NOW))

    claims = service.verify(service.issue("user-1", 7))

    assert claims.user_id == "user-1"
    assert claims.token_version == 7


def test_verify_rejects_a_token_signed_with_a_different_secret():
    issuer = JwtPasswordResetTokenService(secret=_SECRET, clock=_at(_NOW))
    attacker = JwtPasswordResetTokenService(secret="other-secret-key-at-least-32-bytes!!", clock=_at(_NOW))

    with pytest.raises(InvalidPasswordResetTokenError):
        attacker.verify(issuer.issue("user-1", 0))


def test_verify_rejects_an_expired_token():
    # Issued two hours ago with a one-hour lifetime, so it is already expired right now.
    issued = JwtPasswordResetTokenService(
        secret=_SECRET, ttl=timedelta(hours=1), clock=_at(_NOW - timedelta(hours=2))
    )
    service = JwtPasswordResetTokenService(secret=_SECRET, clock=_at(_NOW))

    with pytest.raises(InvalidPasswordResetTokenError):
        service.verify(issued.issue("user-1", 0))


def test_verify_rejects_garbage():
    service = JwtPasswordResetTokenService(secret=_SECRET, clock=_at(_NOW))

    with pytest.raises(InvalidPasswordResetTokenError):
        service.verify("not.a.jwt")


def test_verify_rejects_an_email_verification_token():
    # A confirmation token (different purpose, same secret) must not pass as a reset token.
    verification = JwtVerificationTokenService(secret=_SECRET, clock=_at(_NOW))
    resets = JwtPasswordResetTokenService(secret=_SECRET, clock=_at(_NOW))

    with pytest.raises(InvalidPasswordResetTokenError):
        resets.verify(verification.issue("user-1"))


def test_verify_rejects_a_token_with_no_purpose():
    resets = JwtPasswordResetTokenService(secret=_SECRET, clock=_at(_NOW))
    bare = jwt.encode({"sub": "user-1"}, _SECRET, algorithm="HS256")

    with pytest.raises(InvalidPasswordResetTokenError):
        resets.verify(bare)


def test_verify_rejects_a_token_missing_the_token_version():
    resets = JwtPasswordResetTokenService(secret=_SECRET, clock=_at(_NOW))
    no_ver = jwt.encode(
        {"sub": "user-1", "purpose": "password_reset"}, _SECRET, algorithm="HS256"
    )

    with pytest.raises(InvalidPasswordResetTokenError):
        resets.verify(no_ver)
