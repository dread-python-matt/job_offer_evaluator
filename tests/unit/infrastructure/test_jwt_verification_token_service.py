from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.domain.errors import InvalidVerificationTokenError
from app.infrastructure.jwt_token_service import JwtTokenService
from app.infrastructure.jwt_verification_token_service import JwtVerificationTokenService

_SECRET = "test-secret-key-at-least-32-bytes-long!"
_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _at(moment: datetime):
    return lambda: moment


def test_issue_then_verify_returns_the_user_id():
    service = JwtVerificationTokenService(secret=_SECRET, ttl=timedelta(hours=24), clock=_at(_NOW))

    token = service.issue("user-1")

    assert service.verify(token) == "user-1"


def test_verify_rejects_a_token_signed_with_a_different_secret():
    issuer = JwtVerificationTokenService(secret=_SECRET, clock=_at(_NOW))
    attacker = JwtVerificationTokenService(secret="other-secret-key-at-least-32-bytes!!", clock=_at(_NOW))

    with pytest.raises(InvalidVerificationTokenError):
        attacker.verify(issuer.issue("user-1"))


def test_verify_rejects_an_expired_token():
    issued = JwtVerificationTokenService(secret=_SECRET, ttl=timedelta(hours=1), clock=_at(_NOW))
    token = issued.issue("user-1")

    later = JwtVerificationTokenService(secret=_SECRET, clock=_at(_NOW + timedelta(hours=2)))

    with pytest.raises(InvalidVerificationTokenError):
        later.verify(token)


def test_verify_rejects_garbage():
    service = JwtVerificationTokenService(secret=_SECRET, clock=_at(_NOW))

    with pytest.raises(InvalidVerificationTokenError):
        service.verify("not.a.jwt")


def test_verify_rejects_a_session_token_lacking_the_verification_purpose():
    # A session JWT (sub + ver, no verification purpose) must not pass as a confirmation
    # token, even though it is validly signed with the same secret.
    sessions = JwtTokenService(secret=_SECRET, clock=_at(_NOW))
    verifier = JwtVerificationTokenService(secret=_SECRET, clock=_at(_NOW))

    with pytest.raises(InvalidVerificationTokenError):
        verifier.verify(sessions.issue("user-1", token_version=0))


def test_verify_rejects_a_token_with_a_foreign_purpose():
    verifier = JwtVerificationTokenService(secret=_SECRET, clock=_at(_NOW))
    foreign = jwt.encode({"sub": "user-1", "purpose": "password_reset"}, _SECRET, algorithm="HS256")

    with pytest.raises(InvalidVerificationTokenError):
        verifier.verify(foreign)
