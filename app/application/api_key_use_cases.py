from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.ports import (
    ApiKeyRecord,
    ApiKeyRepository,
    ApiKeyValidator,
    KeyCipher,
    UserProviderSpendProvider,
)
from app.domain.api_keys import mask_key
from app.domain.api_providers import company_for_provider, is_supported_provider
from app.domain.errors import (
    ApiKeyAlreadyExistsError,
    ApiKeyNotFoundError,
    UnsupportedApiProviderError,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApiKeyView:
    """What a caller may see about a stored key: the provider, a masked hint, the key's
    own budget limit, and its derived usage. Never carries the key (plaintext or cipher)."""

    api_provider: str
    key_hint: str
    limit_usd: float
    used_usd: float


def _view_with_usage(
    record: ApiKeyRecord, spend: UserProviderSpendProvider
) -> ApiKeyView:
    used = spend.spend_since(
        record.user_id, company_for_provider(record.api_provider), record.tracking_since
    )
    return ApiKeyView(
        api_provider=record.api_provider,
        key_hint=record.key_hint,
        limit_usd=record.limit_usd,
        used_usd=used,
    )


class AddApiKeyUseCase:
    """Registers a user's own provider API key: rejects unsupported providers and
    duplicates, confirms the key works against the provider before storing, then persists
    only its ciphertext plus a masked hint and the key's own budget. A freshly added key
    has anchored its usage window at now, so its usage starts at $0."""

    def __init__(
        self,
        repository: ApiKeyRepository,
        cipher: KeyCipher,
        validator: ApiKeyValidator,
        clock: Callable[[], datetime] = _utc_now,
        on_change: Callable[[str], None] = lambda _user_id: None,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._validator = validator
        self._clock = clock
        self._on_change = on_change

    def execute(
        self, user_id: str, api_provider: str, key: str, limit_usd: float
    ) -> ApiKeyView:
        if not is_supported_provider(api_provider):
            raise UnsupportedApiProviderError(api_provider)
        if self._repository.get(user_id, api_provider) is not None:
            raise ApiKeyAlreadyExistsError(api_provider)
        self._validator.validate(api_provider, key)  # raises InvalidApiKeyError
        now = self._clock()
        record = ApiKeyRecord(
            user_id=user_id,
            api_provider=api_provider,
            key_ciphertext=self._cipher.encrypt(key),
            key_hint=mask_key(key),
            limit_usd=limit_usd,
            tracking_since=now,
            created_at=now,
        )
        self._repository.add(record)
        # The user's available providers changed — let derived per-user state (e.g. the
        # cached model picker) refresh instead of serving a stale list.
        self._on_change(user_id)
        return ApiKeyView(
            api_provider=api_provider, key_hint=record.key_hint, limit_usd=limit_usd, used_usd=0.0
        )


class ListApiKeysUseCase:
    """Lists a user's stored keys as masked views, each with its budget and its own derived
    usage (spend on that provider since the key's anchor)."""

    def __init__(
        self, repository: ApiKeyRepository, spend: UserProviderSpendProvider
    ) -> None:
        self._repository = repository
        self._spend = spend

    def execute(self, user_id: str) -> list[ApiKeyView]:
        return [
            _view_with_usage(record, self._spend)
            for record in self._repository.list_for_user(user_id)
        ]


class SetApiKeyBudgetUseCase:
    """Changes only the spend limit of an existing key, leaving the key and its usage
    window untouched. Raises if the user has no key for that provider."""

    def __init__(
        self, repository: ApiKeyRepository, spend: UserProviderSpendProvider
    ) -> None:
        self._repository = repository
        self._spend = spend

    def execute(self, user_id: str, api_provider: str, limit_usd: float) -> ApiKeyView:
        if not self._repository.update_budget(user_id, api_provider, limit_usd):
            raise ApiKeyNotFoundError(api_provider)
        record = self._repository.get(user_id, api_provider)
        return _view_with_usage(record, self._spend)


class DeleteApiKeyUseCase:
    """Removes a user's key for a provider. Raises if there was nothing to delete."""

    def __init__(
        self,
        repository: ApiKeyRepository,
        on_change: Callable[[str], None] = lambda _user_id: None,
    ) -> None:
        self._repository = repository
        self._on_change = on_change

    def execute(self, user_id: str, api_provider: str) -> None:
        if not self._repository.delete(user_id, api_provider):
            raise ApiKeyNotFoundError(api_provider)
        # The user's available providers changed — refresh derived per-user state.
        self._on_change(user_id)
