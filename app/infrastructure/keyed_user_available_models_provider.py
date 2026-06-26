import logging
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.application.ports import (
    ApiKeyRepository,
    AvailableModel,
    AvailableModelsProvider,
    KeyCipher,
    UserAvailableModelsProvider,
)

_logger = logging.getLogger(__name__)

ProviderFactory = Callable[[str, str], AvailableModelsProvider]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KeyedUserAvailableModelsProvider(UserAvailableModelsProvider):
    """Discovers a user's available models from their own stored provider keys: for each
    key, decrypts it, lists that provider's models, and aggregates. A provider whose
    listing fails (e.g. a revoked key) is skipped so one bad key doesn't break the whole
    picker; a user with no keys gets an empty list (require own key)."""

    def __init__(
        self, repository: ApiKeyRepository, cipher: KeyCipher, provider_factory: ProviderFactory
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._provider_factory = provider_factory

    def list_models(self, user_id: str) -> list[AvailableModel]:
        result: list[AvailableModel] = []
        for record in self._repository.list_for_user(user_id):
            key = self._cipher.decrypt(record.key_ciphertext)
            provider = self._provider_factory(record.api_provider, key)
            try:
                result.extend(provider.list_models())
            except Exception:  # noqa: BLE001 - one bad key must not break the picker
                _logger.warning(
                    "Could not list models for provider %s; skipping", record.api_provider,
                    exc_info=True,
                )
        return result


class CachingUserAvailableModelsProvider(UserAvailableModelsProvider):
    """Caches each user's model list for `ttl_seconds` so UI loads and model switches don't
    re-list every provider every time. Only successful results are cached, per user; errors
    propagate and leave any existing cache untouched. The cache is a bounded LRU
    (`max_entries`) so it can't grow without limit as users accumulate."""

    def __init__(
        self,
        inner: UserAvailableModelsProvider,
        ttl_seconds: float,
        clock: Callable[[], datetime] = _utc_now,
        max_entries: int = 1024,
    ) -> None:
        self._inner = inner
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._max_entries = max_entries
        self._cache: OrderedDict[str, tuple[list[AvailableModel], datetime]] = OrderedDict()

    def list_models(self, user_id: str) -> list[AvailableModel]:
        cached = self._cache.get(user_id)
        if cached is not None and self._ttl > timedelta(0):
            models, fetched_at = cached
            if self._clock() - fetched_at < self._ttl:
                self._cache.move_to_end(user_id)  # mark as most-recently-used
                return models
        models = self._inner.list_models(user_id)
        self._cache[user_id] = (models, self._clock())
        self._cache.move_to_end(user_id)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)  # evict the least-recently-used user
        return models

    def invalidate(self, user_id: str) -> None:
        """Drop this user's cached list so the next call re-discovers their models. Called
        when their keys change (add/delete) so the picker reflects the new set at once
        instead of waiting out the TTL."""
        self._cache.pop(user_id, None)
