import asyncio

import pytest

from app.application.ports import ModelLimits, ModelLimitsRegistry
from app.infrastructure.rate_limiting import (
    TokenBucketRateLimiter,
    build_google_pace_limiter,
    effective_google_rpm,
)


class _FakeLimitsRegistry(ModelLimitsRegistry):
    def __init__(self, limits: dict[str, ModelLimits]) -> None:
        self._limits = limits

    def get_limits(self, model: str) -> ModelLimits | None:
        return self._limits.get(model)


class FakeClock:
    """Deterministic clock: `sleep` advances virtual time instead of really waiting, so the
    token bucket's pacing can be asserted without wall-clock delays."""

    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def _acquire_n(limiter: TokenBucketRateLimiter, n: int) -> None:
    async def run() -> None:
        for _ in range(n):
            await limiter.acquire()

    asyncio.run(run())


def test_allows_up_to_the_rate_without_waiting():
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(10, _time=clock.time, _asleep=clock.sleep)

    _acquire_n(limiter, 10)

    assert clock.now == 0.0  # the first `rate` calls in a window never wait


def test_blocks_until_a_token_refills_once_the_bucket_is_empty():
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(10, _time=clock.time, _asleep=clock.sleep)

    _acquire_n(limiter, 11)  # 11th must wait for one token to refill

    # 10 tokens/minute -> one token every 6 seconds.
    assert clock.now == pytest.approx(6.0)


def test_refills_over_time_so_steady_state_matches_the_rate():
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(60, _time=clock.time, _asleep=clock.sleep)

    _acquire_n(limiter, 90)  # 60 free, then 30 more at 1/sec (60/min)

    assert clock.now == pytest.approx(30.0)


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(0)


def test_max_burst_one_serves_the_first_call_immediately():
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(10, max_burst=1, _time=clock.time, _asleep=clock.sleep)

    _acquire_n(limiter, 1)

    assert clock.now == 0.0


def test_max_burst_one_forbids_a_full_rate_burst_and_spaces_calls_evenly():
    # The bug this guards: a bucket sized to the rate dispenses a whole minute's calls at once
    # and *then* keeps refilling, so ~2x the cap escapes in the first 60s window. max_burst=1
    # forces even spacing (one per 6s at 10/min), so 10 calls take 9*6s, not 0s.
    clock = FakeClock()
    limiter = TokenBucketRateLimiter(10, max_burst=1, _time=clock.time, _asleep=clock.sleep)

    _acquire_n(limiter, 10)

    assert clock.now == pytest.approx(54.0)


def test_max_burst_must_be_at_least_one():
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(10, max_burst=0)


def test_effective_google_rpm_uses_the_models_real_rpm_with_a_safety_margin():
    registry = _FakeLimitsRegistry({"gemini-2.5-pro": ModelLimits(rpm=5, tpm=0, rpd=0)})

    # 5 RPM minus ~10% -> 4. A flat fallback of 10 would over-pace this model straight into 429s.
    assert effective_google_rpm("gemini-2.5-pro", registry, 10) == 4


def test_effective_google_rpm_falls_back_to_configured_for_an_unknown_model():
    registry = _FakeLimitsRegistry({})

    assert effective_google_rpm("gemini-unknown", registry, 10) == 9


def test_effective_google_rpm_never_drops_below_one():
    registry = _FakeLimitsRegistry({"gemini-1.5-pro": ModelLimits(rpm=2, tpm=0, rpd=0)})

    assert effective_google_rpm("gemini-1.5-pro", registry, 10) == 1


def test_effective_google_rpm_is_none_when_pacing_is_disabled():
    registry = _FakeLimitsRegistry({"gemini-2.5-flash": ModelLimits(rpm=10, tpm=0, rpd=0)})

    assert effective_google_rpm("gemini-2.5-flash", registry, 0) is None


def test_effective_google_rpm_splits_the_budget_across_workers():
    registry = _FakeLimitsRegistry({"gemini-2.5-flash": ModelLimits(rpm=10, tpm=0, rpd=0)})

    # Single worker: 10 RPM minus ~10% -> 9. Four workers each pace to a quarter of that (9 // 4)
    # so the fleet's aggregate client-side rate stays under the one per-project provider cap.
    assert effective_google_rpm("gemini-2.5-flash", registry, 10, workers=1) == 9
    assert effective_google_rpm("gemini-2.5-flash", registry, 10, workers=4) == 2


def test_effective_google_rpm_never_drops_below_one_even_with_many_workers():
    registry = _FakeLimitsRegistry({"gemini-2.5-pro": ModelLimits(rpm=5, tpm=0, rpd=0)})

    assert effective_google_rpm("gemini-2.5-pro", registry, 10, workers=100) == 1


def test_build_google_pace_limiter_returns_a_limiter_for_a_configured_model():
    registry = _FakeLimitsRegistry({"gemini-2.5-pro": ModelLimits(rpm=5, tpm=0, rpd=0)})

    limiter = build_google_pace_limiter("gemini-2.5-pro", registry, 10)

    assert isinstance(limiter, TokenBucketRateLimiter)


def test_build_google_pace_limiter_is_none_when_pacing_is_disabled():
    registry = _FakeLimitsRegistry({})

    assert build_google_pace_limiter("gemini-2.5-flash", registry, 0) is None
