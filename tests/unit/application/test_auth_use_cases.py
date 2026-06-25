from datetime import datetime, timezone

import pytest

from app.application.auth_use_cases import (
    AuthenticateUserUseCase,
    ChangePasswordUseCase,
    RegisterUserUseCase,
    VerifyEmailUseCase,
)
from app.domain.auth import User
from app.domain.errors import (
    EmailAlreadyRegisteredError,
    EmailNotDeliverableError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidVerificationTokenError,
)
from tests.fakes import (
    FakeEmailSender,
    FakeEmailValidator,
    FakePasswordHasher,
    FakeTokenService,
    FakeUserRepository,
    FakeVerificationTokenService,
)

_VERIFY_LINK = "https://app.test/verify-email?token="


# --- RegisterUserUseCase ---


def _register_use_case(
    users=None,
    ids=None,
    validator=None,
    sender=None,
    verification_tokens=None,
):
    issued = iter(ids or ["user-1", "user-2", "user-3"])
    return RegisterUserUseCase(
        users=users or FakeUserRepository(),
        hasher=FakePasswordHasher(),
        email_validator=validator or FakeEmailValidator(),
        verification_tokens=verification_tokens or FakeVerificationTokenService(),
        email_sender=sender or FakeEmailSender(),
        link_builder=lambda token: f"{_VERIFY_LINK}{token}",
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


def test_register_creates_an_unverified_user():
    use_case = _register_use_case()

    user = use_case.execute(email="dev@example.com", password="correct horse battery")

    assert user.email_verified is False


def test_register_rejects_an_undeliverable_email_without_creating_a_user():
    repo = FakeUserRepository()
    use_case = _register_use_case(users=repo, validator=FakeEmailValidator(deliverable=False))

    with pytest.raises(EmailNotDeliverableError):
        use_case.execute(email="dev@nonexistent.invalid", password="correct horse battery")

    assert repo.get_by_email("dev@nonexistent.invalid") is None


def test_register_sends_a_confirmation_email_with_the_verification_link():
    sender = FakeEmailSender()
    tokens = FakeVerificationTokenService()
    use_case = _register_use_case(sender=sender, verification_tokens=tokens, ids=["user-1"])

    use_case.execute(email="dev@example.com", password="correct horse battery")

    assert len(sender.sent) == 1
    message = sender.sent[0]
    assert message["to"] == "dev@example.com"
    # The body carries the link built from the freshly issued verification token.
    assert f"{_VERIFY_LINK}{tokens.issue('user-1')}" in message["body"]


def test_register_does_not_send_an_email_when_the_address_is_undeliverable():
    sender = FakeEmailSender()
    use_case = _register_use_case(sender=sender, validator=FakeEmailValidator(deliverable=False))

    with pytest.raises(EmailNotDeliverableError):
        use_case.execute(email="dev@nonexistent.invalid", password="correct horse battery")

    assert sender.sent == []


# --- AuthenticateUserUseCase ---


def _existing_user(*, email_verified: bool = True) -> User:
    return User(
        id="user-1",
        email="dev@example.com",
        password_hash="hashed:correct horse battery",
        token_version=3,
        created_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        email_verified=email_verified,
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


def test_authenticate_rejects_a_user_whose_email_is_not_verified():
    repo = FakeUserRepository([_existing_user(email_verified=False)])
    use_case = _authenticate_use_case(repo)

    with pytest.raises(EmailNotVerifiedError):
        use_case.execute(email="dev@example.com", password="correct horse battery")


# --- VerifyEmailUseCase ---


def _verify_email_use_case(users, verification_tokens=None):
    return VerifyEmailUseCase(
        users=users,
        verification_tokens=verification_tokens or FakeVerificationTokenService(),
        tokens=FakeTokenService(),
    )


def test_verify_email_marks_the_user_verified_and_returns_a_session_token():
    repo = FakeUserRepository([_existing_user(email_verified=False)])
    verification_tokens = FakeVerificationTokenService()
    use_case = _verify_email_use_case(repo, verification_tokens)

    user, session = use_case.execute(verification_tokens.issue("user-1"))

    assert user.email_verified is True
    assert repo.get_by_id("user-1").email_verified is True
    assert session == "user-1:3"  # FakeTokenService encodes user_id:token_version


def test_verify_email_rejects_a_malformed_token():
    repo = FakeUserRepository([_existing_user(email_verified=False)])
    use_case = _verify_email_use_case(repo)

    with pytest.raises(InvalidVerificationTokenError):
        use_case.execute("not-a-valid-token")

    assert repo.get_by_id("user-1").email_verified is False


def test_verify_email_rejects_a_token_for_an_unknown_user():
    repo = FakeUserRepository()  # no users
    verification_tokens = FakeVerificationTokenService()
    use_case = _verify_email_use_case(repo, verification_tokens)

    with pytest.raises(InvalidVerificationTokenError):
        use_case.execute(verification_tokens.issue("ghost"))


def test_verify_email_is_idempotent_for_an_already_verified_user():
    repo = FakeUserRepository([_existing_user(email_verified=True)])
    verification_tokens = FakeVerificationTokenService()
    use_case = _verify_email_use_case(repo, verification_tokens)

    user, session = use_case.execute(verification_tokens.issue("user-1"))

    assert user.email_verified is True
    assert session == "user-1:3"


# --- ChangePasswordUseCase ---

_CURRENT = "correct horse battery"
_NEW_PASSWORD = "a brand new passphrase"


def _change_password_use_case(users):
    return ChangePasswordUseCase(
        users=users, hasher=FakePasswordHasher(), tokens=FakeTokenService()
    )


def test_change_password_replaces_the_hash_so_the_new_password_verifies():
    repo = FakeUserRepository([_existing_user()])
    use_case = _change_password_use_case(repo)

    use_case.execute(user_id="user-1", current_password=_CURRENT, new_password=_NEW_PASSWORD)

    stored = repo.get_by_id("user-1")
    assert stored.password_hash == f"hashed:{_NEW_PASSWORD}"


def test_change_password_bumps_token_version_to_invalidate_existing_sessions():
    repo = FakeUserRepository([_existing_user()])  # token_version starts at 3
    use_case = _change_password_use_case(repo)

    updated, _ = use_case.execute(
        user_id="user-1", current_password=_CURRENT, new_password=_NEW_PASSWORD
    )

    assert updated.token_version == 4
    assert repo.get_by_id("user-1").token_version == 4


def test_change_password_returns_a_session_token_for_the_new_version():
    repo = FakeUserRepository([_existing_user()])
    use_case = _change_password_use_case(repo)

    _, session = use_case.execute(
        user_id="user-1", current_password=_CURRENT, new_password=_NEW_PASSWORD
    )

    assert session == "user-1:4"  # FakeTokenService encodes user_id:token_version


def test_change_password_rejects_a_wrong_current_password_and_leaves_it_unchanged():
    repo = FakeUserRepository([_existing_user()])
    use_case = _change_password_use_case(repo)

    with pytest.raises(InvalidCredentialsError):
        use_case.execute(
            user_id="user-1", current_password="not my password", new_password=_NEW_PASSWORD
        )

    stored = repo.get_by_id("user-1")
    assert stored.password_hash == "hashed:correct horse battery"
    assert stored.token_version == 3
