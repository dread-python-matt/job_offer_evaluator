import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from app.application.ports import PasswordHasher, TokenService, UserRepository
from app.domain.auth import User
from app.domain.errors import EmailAlreadyRegisteredError, InvalidCredentialsError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterUserUseCase:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._id_factory = id_factory
        self._clock = clock

    def execute(self, email: str, password: str) -> User:
        email = _normalize_email(email)
        if self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)
        user = User(
            id=self._id_factory(),
            email=email,
            password_hash=self._hasher.hash(password),
            token_version=0,
            created_at=self._clock(),
        )
        self._users.add(user)
        return user


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
        token = self._tokens.issue(user.id, user.token_version)
        return user, token
