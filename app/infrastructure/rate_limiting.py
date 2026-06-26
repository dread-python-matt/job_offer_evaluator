import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol


class AsyncRateLimiter(Protocol):
    """Paces outbound calls. `acquire()` returns when the caller may proceed, awaiting
    (without busy-waiting) while the limit is saturated."""

    async def acquire(self) -> None: ...


class TokenBucketRateLimiter:
    """Async token bucket pacing calls to a fixed rate-per-minute, shared across concurrent
    tasks. Used to keep the request rate to a provider under a free-tier RPM cap so a burst
    of concurrent scoring calls can't trip a 429 (e.g. Gemini free tier = 10 requests/min).

    The bucket holds at most `rate_per_minute` tokens and refills continuously at that rate,
    so over any 60s window at most `rate_per_minute` calls proceed. `acquire()` takes a token
    immediately when one is available, otherwise sleeps just long enough for the next to
    refill. A lock serializes waiters into FIFO order and keeps the token maths race-free."""

    def __init__(
        self,
        rate_per_minute: int,
        *,
        _time: Callable[[], float] = time.monotonic,
        _asleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self._capacity = float(rate_per_minute)
        self._refill_per_second = rate_per_minute / 60.0
        self._tokens = float(rate_per_minute)
        self._time = _time
        self._asleep = _asleep
        self._updated_at = _time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await self._asleep((1.0 - self._tokens) / self._refill_per_second)

    def _refill(self) -> None:
        now = self._time()
        elapsed = now - self._updated_at
        self._updated_at = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
