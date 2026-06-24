from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.application.ports import AvailableModel, AvailableModelsProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CachingAvailableModelsProvider(AvailableModelsProvider):
    """Caches a wrapped provider's model list for `ttl_seconds` so UI loads and model
    switches don't hit the provider's models API every time. Only successful results
    are cached; errors propagate and leave any existing cache untouched."""

    def __init__(
        self,
        inner: AvailableModelsProvider,
        ttl_seconds: float,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._inner = inner
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._cache: tuple[list[AvailableModel], datetime] | None = None

    def list_models(self) -> list[AvailableModel]:
        if self._cache is not None and self._ttl > timedelta(0):
            models, fetched_at = self._cache
            if self._clock() - fetched_at < self._ttl:
                return models
        models = self._inner.list_models()
        self._cache = (models, self._clock())
        return models
