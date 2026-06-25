import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.application.ports import BudgetRepository, BudgetStatusReader, UserSpendProvider
from app.domain.budget import BudgetStatus
from app.domain.errors import CostUnavailableError

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BudgetService(BudgetStatusReader):
    """Per-user budget: combines a user's persisted settings with their (token-accounted)
    spend to produce a status, and applies the two mutations the API exposes — setting
    the limit and resetting usage (which moves that user's tracking anchor to now).

    `spend_provider` is optional: without it the limit is still settable, but `used_usd`
    is reported as None and the budget never blocks. The spend figure is cached per
    (user, anchor) for `cache_ttl_seconds` so a burst of AI matches doesn't recompute it
    every request. A reset moves the anchor and so transparently invalidates the cache."""

    def __init__(
        self,
        repository: BudgetRepository,
        spend_provider: UserSpendProvider | None,
        clock: Callable[[], datetime] = _utc_now,
        cache_ttl_seconds: float = 0.0,
    ) -> None:
        self._repository = repository
        self._spend_provider = spend_provider
        self._clock = clock
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        # user_id -> (anchor, spend, fetched_at)
        self._cache: dict[str, tuple[datetime, float, datetime]] = {}

    def status(self, user_id: str) -> BudgetStatus:
        settings = self._repository.load(user_id)
        return BudgetStatus(
            limit_usd=settings.limit_usd,
            used_usd=self._used_since(user_id, settings.tracking_since),
            tracking_since=settings.tracking_since,
        )

    def set_limit(self, user_id: str, limit_usd: float) -> BudgetStatus:
        settings = self._repository.load(user_id)
        self._repository.save(user_id, replace(settings, limit_usd=limit_usd))
        return self.status(user_id)

    def reset_usage(self, user_id: str) -> BudgetStatus:
        settings = self._repository.load(user_id)
        self._repository.save(user_id, replace(settings, tracking_since=self._clock()))
        return self.status(user_id)

    def _used_since(self, user_id: str, start: datetime) -> float | None:
        if self._spend_provider is None:
            return None
        cached = self._cached_spend(user_id, start)
        if cached is not None:
            return cached
        try:
            spend = self._spend_provider.spend_since(user_id, start)
        except CostUnavailableError as exc:
            _logger.warning("Spend figure unavailable; reporting usage as unknown: %s", exc)
            return None
        self._cache[user_id] = (start, spend, self._clock())
        return spend

    def _cached_spend(self, user_id: str, start: datetime) -> float | None:
        entry = self._cache.get(user_id)
        if entry is None or self._cache_ttl <= timedelta(0):
            return None
        anchor, spend, fetched_at = entry
        if anchor != start or self._clock() - fetched_at >= self._cache_ttl:
            return None
        return spend
