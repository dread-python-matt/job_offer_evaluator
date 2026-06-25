from app.domain.auth import User
from app.scripts.verify_link import build_verification_link
from tests.fakes import FakeUserRepository, FakeVerificationTokenService


def _user(email: str = "dev@example.com") -> User:
    return User(id="user-1", email=email, password_hash="hashed:x")


def test_build_verification_link_for_an_existing_user():
    repo = FakeUserRepository([_user()])
    tokens = FakeVerificationTokenService()

    link = build_verification_link(
        repo, tokens, lambda token: f"https://app.test/verify-email?token={token}", "dev@example.com"
    )

    assert link == f"https://app.test/verify-email?token={tokens.issue('user-1')}"


def test_build_verification_link_normalizes_the_email():
    repo = FakeUserRepository([_user()])
    tokens = FakeVerificationTokenService()

    link = build_verification_link(repo, tokens, lambda token: token, "  DEV@Example.COM ")

    assert link == tokens.issue("user-1")


def test_build_verification_link_returns_none_for_an_unknown_email():
    repo = FakeUserRepository()
    tokens = FakeVerificationTokenService()

    assert build_verification_link(repo, tokens, lambda token: token, "nobody@example.com") is None
