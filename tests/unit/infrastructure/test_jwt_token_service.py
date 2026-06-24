from datetime import datetime, timedelta, timezone

import pytest

from app.application.ports import TokenClaims
from app.domain.errors import AuthenticationError
from app.infrastructure.jwt_token_service import JwtTokenService


def _at(moment: datetime):
    return lambda: moment


_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def test_issue_then_verify_round_trips_the_claims():
    service = JwtTokenService(secret="test-secret-key-at-least-32-bytes-long!", ttl=timedelta(days=7), clock=_at(_NOW))

    token = service.issue(user_id="user-1", token_version=4)

    assert service.verify(token) == TokenClaims(user_id="user-1", token_version=4)


def test_verify_rejects_a_token_signed_with_a_different_secret():
    issuer = JwtTokenService(secret="real-secret-key-at-least-32-bytes-long!", clock=_at(_NOW))
    attacker_view = JwtTokenService(secret="other-secret-key-at-least-32-bytes-long", clock=_at(_NOW))
    token = issuer.issue(user_id="user-1", token_version=0)

    with pytest.raises(AuthenticationError):
        attacker_view.verify(token)


def test_verify_rejects_an_expired_token():
    issued_at = JwtTokenService(secret="test-secret-key-at-least-32-bytes-long!", ttl=timedelta(minutes=1), clock=_at(_NOW))
    token = issued_at.issue(user_id="user-1", token_version=0)

    later = JwtTokenService(secret="test-secret-key-at-least-32-bytes-long!", clock=_at(_NOW + timedelta(minutes=2)))

    with pytest.raises(AuthenticationError):
        later.verify(token)


def test_verify_rejects_garbage():
    service = JwtTokenService(secret="test-secret-key-at-least-32-bytes-long!", clock=_at(_NOW))

    with pytest.raises(AuthenticationError):
        service.verify("not.a.jwt")
