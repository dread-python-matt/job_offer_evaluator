import asyncio

import pytest

from app.infrastructure.rate_limiting import TokenBucketRateLimiter


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
