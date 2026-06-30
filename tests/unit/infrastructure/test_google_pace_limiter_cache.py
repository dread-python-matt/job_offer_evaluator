from app.application.ports import ModelLimits, ModelLimitsRegistry
from app.infrastructure.google_pace_limiter_cache import GooglePaceLimiterCache
from app.infrastructure.rate_limiting import TokenBucketRateLimiter


class _FakeLimitsRegistry(ModelLimitsRegistry):
    def __init__(self, limits: dict[str, ModelLimits]) -> None:
        self._limits = limits

    def get_limits(self, model: str) -> ModelLimits | None:
        return self._limits.get(model)


_REGISTRY = _FakeLimitsRegistry({"gemini-2.5-flash": ModelLimits(rpm=10, tpm=0, rpd=0)})


def test_returns_a_limiter_and_reuses_it_for_the_same_user_and_model():
    cache = GooglePaceLimiterCache(_REGISTRY, configured_rpm=10)

    first = cache.get("user-1", "gemini-2.5-flash")
    second = cache.get("user-1", "gemini-2.5-flash")

    assert isinstance(first, TokenBucketRateLimiter)
    assert first is second  # cached, not rebuilt


def test_distinct_users_or_models_get_distinct_limiters():
    cache = GooglePaceLimiterCache(_REGISTRY, configured_rpm=10)

    assert cache.get("user-1", "gemini-2.5-flash") is not cache.get(
        "user-2", "gemini-2.5-flash"
    )


def test_returns_none_when_pacing_is_disabled():
    cache = GooglePaceLimiterCache(_REGISTRY, configured_rpm=0)

    assert cache.get("user-1", "gemini-2.5-flash") is None


def test_cache_is_bounded_and_evicts_least_recently_used():
    cache = GooglePaceLimiterCache(_REGISTRY, configured_rpm=10, max_entries=2)

    a = cache.get("user-1", "gemini-2.5-flash")
    cache.get("user-2", "gemini-2.5-flash")
    cache.get("user-1", "gemini-2.5-flash")  # touch user-1 so user-2 is now least-recent
    cache.get("user-3", "gemini-2.5-flash")  # evicts user-2

    assert len(cache._limiters) == 2
    # user-1 was rebuilt? No — it stayed cached (most-recently-used before user-3), so identity holds.
    assert cache.get("user-1", "gemini-2.5-flash") is a
    # user-2 was evicted, so it is rebuilt as a new instance.
    assert ("user-2", "gemini-2.5-flash") not in cache._limiters
