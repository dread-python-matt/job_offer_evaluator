from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.application.ports import RateLimiter
from app.domain.errors import RateLimitExceededError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryRateLimiter(RateLimiter):
    """Fixed-window attempt counter held in process memory.

    Correct for a single worker only: the counts live in this process, so a multi-worker
    deployment would let each worker throttle independently. Swap in a shared-store adapter
    (e.g. Redis) for that — the `RateLimiter` port stays the same. The coarse counting here
    relies only on CPython dict atomicity, which is sufficient for its purpose.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window
        self._clock = clock
        # key -> (window_start, failure_count)
        self._windows: dict[str, tuple[datetime, int]] = {}

    def check(self, key: str) -> None:
        window = self._live_window(key)
        if window is None:
            return
        start, count = window
        if count >= self._max_attempts:
            remaining = (start + self._window) - self._clock()
            raise RateLimitExceededError(
                retry_after_seconds=max(int(remaining.total_seconds()) + 1, 1)
            )

    def record_failure(self, key: str) -> None:
        window = self._live_window(key)
        if window is None:
            self._windows[key] = (self._clock(), 1)
        else:
            start, count = window
            self._windows[key] = (start, count + 1)

    def reset(self, key: str) -> None:
        self._windows.pop(key, None)

    def _live_window(self, key: str) -> tuple[datetime, int] | None:
        """The current (window_start, count) for `key`, or None when there is no window or
        the existing one has expired — an expired window is treated as a clean slate."""
        window = self._windows.get(key)
        if window is None:
            return None
        start, _ = window
        if self._clock() - start >= self._window:
            return None
        return window
