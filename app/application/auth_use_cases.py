import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from app.application.ports import (
    EmailSender,
    EmailValidator,
    PasswordHasher,
    PasswordResetTokenService,
    TokenService,
    UserRepository,
    VerificationTokenService,
)
from app.domain.auth import User
from app.domain.errors import (
    EmailAlreadyRegisteredError,
    EmailNotDeliverableError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidVerificationTokenError,
)

_CONFIRMATION_SUBJECT = "Confirm your email address"


def _confirmation_body(link: str) -> str:
    return (
        "Welcome! Please confirm your email address to finish creating your account "
        f"by opening this link:\n\n{link}\n\n"
        "If you didn't sign up, you can safely ignore this email."
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterUserUseCase:
    """Creates an *unverified* account and emails a confirmation link. The account
    cannot be logged into until the link is followed (see VerifyEmailUseCase); no session
    is issued here. The address is checked for deliverability before anything is persisted
    so dead/mistyped domains fail fast."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        email_validator: EmailValidator,
        verification_tokens: VerificationTokenService,
        email_sender: EmailSender,
        link_builder: Callable[[str], str],
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._email_validator = email_validator
        self._verification_tokens = verification_tokens
        self._email_sender = email_sender
        self._link_builder = link_builder
        self._id_factory = id_factory
        self._clock = clock

    def execute(self, email: str, password: str) -> User:
        email = _normalize_email(email)
        if not self._email_validator.is_deliverable(email):
            raise EmailNotDeliverableError(email)
        if self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)
        user = User(
            id=self._id_factory(),
            email=email,
            password_hash=self._hasher.hash(password),
            token_version=0,
            created_at=self._clock(),
            email_verified=False,
        )
        self._users.add(user)
        self._send_confirmation(user)
        return user

    def _send_confirmation(self, user: User) -> None:
        token = self._verification_tokens.issue(user.id)
        link = self._link_builder(token)
        self._email_sender.send(
            to=user.email,
            subject=_CONFIRMATION_SUBJECT,
            body=_confirmation_body(link),
        )


class AuthenticateUserUseCase:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens

    def execute(self, email: str, password: str) -> tuple[User, str]:
        user = self._users.get_by_email(_normalize_email(email))
        if user is None or not self._hasher.verify(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password")
        if not user.email_verified:
            raise EmailNotVerifiedError("Email address has not been confirmed")
        token = self._tokens.issue(user.id, user.token_version)
        return user, token


class VerifyEmailUseCase:
    """Completes registration: validates a confirmation token, marks the account verified,
    and issues a session token so following the link logs the user straight in. Idempotent
    for an already-verified account."""

    def __init__(
        self,
        users: UserRepository,
        verification_tokens: VerificationTokenService,
        tokens: TokenService,
    ) -> None:
        self._users = users
        self._verification_tokens = verification_tokens
        self._tokens = tokens

    def execute(self, token: str) -> tuple[User, str]:
        user_id = self._verification_tokens.verify(token)
        user = self._users.get_by_id(user_id)
        if user is None:
            raise InvalidVerificationTokenError("No account for this confirmation token")
        if not user.email_verified:
            self._users.mark_email_verified(user.id)
            user = replace(user, email_verified=True)
        session = self._tokens.issue(user.id, user.token_version)
        return user, session


class ChangePasswordUseCase:
    """Changes an authenticated user's password. The current password must be supplied and
    verified, then the hash is replaced and token_version is bumped — which invalidates
    every previously issued session (logout everywhere else). A fresh session token is
    returned so the caller's current device stays signed in."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens

    def execute(self, user_id: str, current_password: str, new_password: str) -> tuple[User, str]:
        user = self._users.get_by_id(user_id)
        if user is None or not self._hasher.verify(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        new_version = user.token_version + 1
        new_hash = self._hasher.hash(new_password)
        self._users.update_password(user.id, new_hash, new_version)
        updated = replace(user, password_hash=new_hash, token_version=new_version)
        return updated, self._tokens.issue(updated.id, updated.token_version)


_RESET_SUBJECT = "Reset your password"


def _reset_body(link: str) -> str:
    return (
        "We received a request to reset your password. Open this link to choose a new one:"
        f"\n\n{link}\n\n"
        "If you didn't request this, you can safely ignore this email — your password "
        "won't change."
    )


class RequestPasswordResetUseCase:
    """Starts the 'forgot password' flow: if the email belongs to an account, emails a
    single-purpose reset link. Deliberately silent when the email is unknown so the endpoint
    can't be used to discover which addresses are registered (enumeration-resistant)."""

    def __init__(
        self,
        users: UserRepository,
        reset_tokens: PasswordResetTokenService,
        email_sender: EmailSender,
        link_builder: Callable[[str], str],
    ) -> None:
        self._users = users
        self._reset_tokens = reset_tokens
        self._email_sender = email_sender
        self._link_builder = link_builder

    def execute(self, email: str) -> None:
        user = self._users.get_by_email(_normalize_email(email))
        if user is None:
            return
        token = self._reset_tokens.issue(user.id)
        link = self._link_builder(token)
        self._email_sender.send(
            to=user.email,
            subject=_RESET_SUBJECT,
            body=_reset_body(link),
        )


class ResetPasswordUseCase:
    """Completes the 'forgot password' flow: validates a reset token, sets the new password,
    and bumps token_version so every previously issued session is invalidated. Following the
    link also confirms the email (it proves ownership). Returns a fresh session token so the
    user lands signed in."""

    def __init__(
        self,
        users: UserRepository,
        reset_tokens: PasswordResetTokenService,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._users = users
        self._reset_tokens = reset_tokens
        self._hasher = hasher
        self._tokens = tokens

    def execute(self, token: str, new_password: str) -> tuple[User, str]:
        user_id = self._reset_tokens.verify(token)
        user = self._users.get_by_id(user_id)
        if user is None:
            raise InvalidPasswordResetTokenError("No account for this reset token")
        new_version = user.token_version + 1
        new_hash = self._hasher.hash(new_password)
        self._users.update_password(user.id, new_hash, new_version)
        if not user.email_verified:
            self._users.mark_email_verified(user.id)
        updated = replace(
            user, password_hash=new_hash, token_version=new_version, email_verified=True
        )
        return updated, self._tokens.issue(updated.id, updated.token_version)
