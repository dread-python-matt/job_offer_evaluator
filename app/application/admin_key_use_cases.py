from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.ports import (
    AdminKeyRecord,
    AdminKeyRepository,
    AdminKeyValidator,
    KeyCipher,
)
from app.domain.api_keys import mask_key


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AdminKeyView:
    """What a caller may see about a stored admin key: a masked hint and when it was saved.
    Never carries the key (plaintext or cipher)."""

    key_hint: str
    created_at: datetime


def _view(record: AdminKeyRecord) -> AdminKeyView:
    return AdminKeyView(key_hint=record.key_hint, created_at=record.created_at)


class SetAdminKeyUseCase:
    """Saves (or rotates) a user's OpenAI admin key: confirms the key can read the org
    costs/usage API before storing, then persists only its ciphertext plus a masked hint.
    Saving when one already exists replaces it."""

    def __init__(
        self,
        repository: AdminKeyRepository,
        cipher: KeyCipher,
        validator: AdminKeyValidator,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._validator = validator
        self._clock = clock

    def execute(self, user_id: str, key: str) -> AdminKeyView:
        self._validator.validate(key)  # raises InvalidAdminKeyError
        record = AdminKeyRecord(
            user_id=user_id,
            key_ciphertext=self._cipher.encrypt(key),
            key_hint=mask_key(key),
            created_at=self._clock(),
        )
        self._repository.upsert(record)
        return _view(record)


class GetAdminKeyUseCase:
    """Returns the user's stored admin key as a masked view, or None when none is saved —
    so the UI can show a 'configured' state without ever exposing the key."""

    def __init__(self, repository: AdminKeyRepository) -> None:
        self._repository = repository

    def execute(self, user_id: str) -> AdminKeyView | None:
        record = self._repository.get(user_id)
        return _view(record) if record is not None else None


class DeleteAdminKeyUseCase:
    """Removes the user's admin key. Idempotent: returns whether a key was actually
    removed, but does not error when there was nothing to delete."""

    def __init__(self, repository: AdminKeyRepository) -> None:
        self._repository = repository

    def execute(self, user_id: str) -> bool:
        return self._repository.delete(user_id)
