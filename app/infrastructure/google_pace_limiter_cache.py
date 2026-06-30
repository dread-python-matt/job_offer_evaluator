from collections import OrderedDict

from app.application.ports import ModelLimitsRegistry
from app.infrastructure.rate_limiting import AsyncRateLimiter, build_google_pace_limiter


class GooglePaceLimiterCache:
    """Per-(user, model) Google/Gemini pace limiter, built lazily and held in a bounded LRU.

    Gemini free-tier RPM is capped per (project, model) and each user brings their own key, so
    every (user, model) pair paces independently at that model's real RPM. The cache is a bounded
    LRU (`max_entries`) so it can't grow without limit as users and models accumulate — matching
    the discipline of the other per-user caches (e.g. `AiScoringContext`).

    `workers` splits each model's RPM budget across worker processes (the cache is per process but
    the provider cap is per project): without it, `WORKERS` workers each pacing to the full RPM
    would aggregate to `WORKERS`x the cap and trip 429s.

    Returns `None` (pacing disabled) for every key when `configured_rpm <= 0`."""

    def __init__(
        self,
        limits_registry: ModelLimitsRegistry,
        configured_rpm: int,
        *,
        workers: int = 1,
        max_entries: int = 512,
    ) -> None:
        self._limits_registry = limits_registry
        self._configured_rpm = configured_rpm
        self._workers = workers
        self._max_entries = max_entries
        self._limiters: OrderedDict[tuple[str, str], AsyncRateLimiter] = OrderedDict()

    def get(self, user_id: str, model: str) -> AsyncRateLimiter | None:
        if self._configured_rpm <= 0:
            return None
        cache_key = (user_id, model)
        if cache_key in self._limiters:
            self._limiters.move_to_end(cache_key)  # mark most-recently-used
            return self._limiters[cache_key]
        limiter = build_google_pace_limiter(
            model, self._limits_registry, self._configured_rpm, self._workers
        )
        assert limiter is not None  # configured_rpm > 0 here, so pacing is enabled
        self._limiters[cache_key] = limiter
        while len(self._limiters) > self._max_entries:
            self._limiters.popitem(last=False)  # evict the least-recently-used entry
        return limiter
