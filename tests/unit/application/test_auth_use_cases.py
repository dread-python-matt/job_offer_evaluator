from datetime import datetime, timezone

import pytest

from app.application.auth_use_cases import AuthenticateUserUseCase, RegisterUserUseCase
from app.domain.auth import User
from app.domain.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository


# --- RegisterUserUseCase ---


def _register_use_case(users=None, ids=None):
    issued = iter(ids or ["user-1", "user-2", "user-3"])
    return RegisterUserUseCase(
        users=users or FakeUserRepository(),
        hasher=FakePasswordHasher(),
        id_factory=lambda: next(issued),
        clock=lambda: datetime(2026, 6, 24, tzinfo=timezone.utc),
    )


def test_register_persists_a_user_with_hashed_password():
    repo = FakeUserRepository()
    use_case = _register_use_case(users=repo)

    user = use_case.execute(email="dev@example.com", password="correct horse battery")

    stored = repo.get_by_email("dev@example.com")
    assert stored is not None
    assert stored.id == user.id
    assert stored.password_hash == "hashed:correct horse battery"
    assert stored.password_hash != "correct horse battery"


def test_register_starts_token_version_at_zero():
    use_case = _register_use_case()

    user = use_case.execute(email="dev@example.com", password="correct horse battery")

    assert user.token_version == 0


def test_register_normalizes_email_to_lowercase_and_trims():
    repo = FakeUserRepository()
    use_case = _register_use_case(users=repo)

    use_case.execute(email="  Dev@Example.COM ", password="correct horse battery")

    assert repo.get_by_email("dev@example.com") is not None


def test_register_rejects_duplicate_email():
    repo = FakeUserRepository()
    use_case = _register_use_case(users=repo)
    use_case.execute(email="dev@example.com", password="correct horse battery")

    with pytest.raises(EmailAlreadyRegisteredError):
        use_case.execute(email="dev@example.com", password="another password!!")


def test_register_treats_differently_cased_emails_as_duplicates():
    repo = FakeUserRepository()
    use_case = _register_use_case(users=repo)
    use_case.execute(email="dev@example.com", password="correct horse battery")

    with pytest.raises(EmailAlreadyRegisteredError):
        use_case.execute(email="DEV@example.com", password="another password!!")


# --- AuthenticateUserUseCase ---


def _existing_user() -> User:
    return User(
        id="user-1",
        email="dev@example.com",
        password_hash="hashed:correct horse battery",
        token_version=3,
        created_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )


def _authenticate_use_case(users):
    return AuthenticateUserUseCase(
        users=users, hasher=FakePasswordHasher(), tokens=FakeTokenService()
    )


def test_authenticate_returns_user_and_token_on_valid_credentials():
    repo = FakeUserRepository([_existing_user()])
    use_case = _authenticate_use_case(repo)

    user, token = use_case.execute(email="dev@example.com", password="correct horse battery")

    assert user.id == "user-1"
    assert token == "user-1:3"  # FakeTokenService encodes user_id:token_version


def test_authenticate_normalizes_email_before_lookup():
    repo = FakeUserRepository([_existing_user()])
    use_case = _authenticate_use_case(repo)

    user, _ = use_case.execute(email="  DEV@example.com ", password="correct horse battery")

    assert user.id == "user-1"


def test_authenticate_rejects_wrong_password():
    repo = FakeUserRepository([_existing_user()])
    use_case = _authenticate_use_case(repo)

    with pytest.raises(InvalidCredentialsError):
        use_case.execute(email="dev@example.com", password="wrong password!!")


def test_authenticate_rejects_unknown_email():
    use_case = _authenticate_use_case(FakeUserRepository())

    with pytest.raises(InvalidCredentialsError):
        use_case.execute(email="nobody@example.com", password="correct horse battery")
