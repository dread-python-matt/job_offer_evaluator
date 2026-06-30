import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.application.ports import ModelLimitsRegistry


class AsyncRateLimiter(Protocol):
    """Paces outbound calls. `acquire()` returns when the caller may proceed, awaiting
    (without busy-waiting) while the limit is saturated."""

    async def acquire(self) -> None: ...


class TokenBucketRateLimiter:
    """Async token bucket pacing calls to a fixed rate-per-minute, shared across concurrent
    tasks. Used to keep the request rate to a provider under a free-tier RPM cap so a burst
    of concurrent scoring calls can't trip a 429 (e.g. Gemini free tier = 10 requests/min).

    The bucket refills continuously at `rate_per_minute` and holds at most `max_burst` tokens
    (default: `rate_per_minute`). `acquire()` takes a token immediately when one is available,
    otherwise sleeps just long enough for the next to refill. A lock serializes waiters into
    FIFO order and keeps the token maths race-free.

    `max_burst` bounds how many calls may fire back-to-back before pacing kicks in. The default
    (capacity == rate) lets a whole minute's worth of calls go at once and *then* keep refilling
    — up to ~2x the rate inside the first 60s window, which trips a hard per-minute provider cap.
    Pass `max_burst=1` to space calls evenly (one per 60/rate seconds) so the cap holds from the
    very first call."""

    def __init__(
        self,
        rate_per_minute: int,
        *,
        max_burst: int | None = None,
        _time: Callable[[], float] = time.monotonic,
        _asleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        if max_burst is not None and max_burst < 1:
            raise ValueError("max_burst must be at least 1")
        self._capacity = float(rate_per_minute if max_burst is None else max_burst)
        self._refill_per_second = rate_per_minute / 60.0
        self._tokens = self._capacity
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


# Pace slightly under the provider's cap so a boundary tick or clock jitter can't trip it.
_RPM_SAFETY_MARGIN = 0.9


def effective_google_rpm(
    model: str,
    limits_registry: ModelLimitsRegistry,
    configured_rpm: int,
    workers: int = 1,
) -> int | None:
    """Requests-per-minute a Google/Gemini model should be paced at, or None when pacing is
    disabled (`configured_rpm <= 0`).

    Gemini free-tier RPM is per (project, model) and varies widely — gemini-1.5-pro is 2 RPM,
    gemini-2.5-pro 5, gemini-2.5-flash 10, flash-lite 30 — so one flat rate over-paces the slow
    models straight into 429s. The per-model cap comes from `limits_registry`; an unknown model
    falls back to `configured_rpm` (the GOOGLE_RPM_LIMIT knob, which also disables pacing at 0).
    A ~10% safety margin absorbs boundary effects against the provider's hard cap.

    The limiter is per process, but the provider cap is per project, so under `workers > 1` the
    budget is split across workers (RPM // workers): each worker paces to its share so the
    fleet's aggregate client-side rate stays under the one shared cap instead of `workers`x it."""
    if configured_rpm <= 0:
        return None
    limits = limits_registry.get_limits(model)
    rpm = limits.rpm if limits is not None else configured_rpm
    return max(1, int(rpm * _RPM_SAFETY_MARGIN) // max(1, workers))


def build_google_pace_limiter(
    model: str,
    limits_registry: ModelLimitsRegistry,
    configured_rpm: int,
    workers: int = 1,
) -> AsyncRateLimiter | None:
    """Client-side pacer for a Google/Gemini model, sized to that model's real free-tier RPM
    (see `effective_google_rpm`, including the per-worker split) so a burst of scoring/translation
    calls can't trip a 429. Returns None when pacing is disabled. Built with `max_burst=1` so
    calls stay evenly spaced and the per-minute cap holds from the first call (a full-capacity
    bucket would otherwise let ~2x the cap through in the first 60s)."""
    rpm = effective_google_rpm(model, limits_registry, configured_rpm, workers)
    if rpm is None:
        return None
    return TokenBucketRateLimiter(rpm, max_burst=1)
