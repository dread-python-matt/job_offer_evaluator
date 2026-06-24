from datetime import datetime, timedelta, timezone

from app.application.ports import AvailableModel, AvailableModelsProvider
from app.infrastructure.caching_available_models_provider import CachingAvailableModelsProvider


class CountingProvider(AvailableModelsProvider):
    def __init__(self, models: list[AvailableModel]) -> None:
        self._models = models
        self.calls = 0

    def list_models(self) -> list[AvailableModel]:
        self.calls += 1
        return self._models


class _ManualClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


_MODELS = [AvailableModel(model="gpt-4o", company="OpenAI")]
_START = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_caches_within_ttl():
    inner = CountingProvider(_MODELS)
    provider = CachingAvailableModelsProvider(inner, ttl_seconds=300, clock=_ManualClock(_START))

    assert provider.list_models() == _MODELS
    provider.list_models()

    assert inner.calls == 1


def test_refetches_after_ttl_expires():
    inner = CountingProvider(_MODELS)
    clock = _ManualClock(_START)
    provider = CachingAvailableModelsProvider(inner, ttl_seconds=300, clock=clock)

    provider.list_models()
    clock.now += timedelta(seconds=301)
    provider.list_models()

    assert inner.calls == 2
