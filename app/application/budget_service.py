import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from app.application.ports import BudgetRepository, BudgetStatusReader, SpendProvider
from app.domain.budget import BudgetStatus
from app.domain.errors import CostUnavailableError

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BudgetService(BudgetStatusReader):
    """Combines the persisted budget settings with live spend to produce a status,
    and applies the two mutations the API exposes: setting the limit and resetting
    usage (which moves the tracking anchor to now).

    `spend_provider` is optional: without it (no admin key) the limit is still
    settable, but `used_usd` is reported as None and the budget never blocks."""

    def __init__(
        self,
        repository: BudgetRepository,
        spend_provider: SpendProvider | None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._spend_provider = spend_provider
        self._clock = clock

    def status(self) -> BudgetStatus:
        settings = self._repository.load()
        return BudgetStatus(
            limit_usd=settings.limit_usd,
            used_usd=self._used_since(settings.tracking_since),
            tracking_since=settings.tracking_since,
        )

    def set_limit(self, limit_usd: float) -> BudgetStatus:
        settings = self._repository.load()
        self._repository.save(replace(settings, limit_usd=limit_usd))
        return self.status()

    def reset_usage(self) -> BudgetStatus:
        settings = self._repository.load()
        self._repository.save(replace(settings, tracking_since=self._clock()))
        return self.status()

    def _used_since(self, start: datetime) -> float | None:
        if self._spend_provider is None:
            return None
        try:
            return self._spend_provider.spend_since(start)
        except CostUnavailableError as exc:
            _logger.warning("Spend figure unavailable; reporting usage as unknown: %s", exc)
            return None
