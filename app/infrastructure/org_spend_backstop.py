from collections.abc import Callable
from datetime import datetime, timezone

from app.application.ports import BudgetStatusReader, SpendProvider
from app.domain.budget import BudgetStatus
from app.domain.errors import CostUnavailableError


def _start_of_utc_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class OrgSpendBackstop(BudgetStatusReader):
    """A global guard on the organization's actual provider spend for the current UTC
    day, independent of any per-user budget — it protects the owner's real bill. Ignores
    `user_id` (the figure is org-wide and can't be attributed per user). Reports
    `used_usd=None` (never blocks) when no spend provider is configured or it is
    unavailable."""

    def __init__(
        self,
        spend_provider: SpendProvider | None,
        limit_usd: float,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._spend_provider = spend_provider
        self._limit_usd = limit_usd
        self._clock = clock

    def status(self, user_id: str) -> BudgetStatus:
        anchor = _start_of_utc_day(self._clock())
        used: float | None = None
        if self._spend_provider is not None:
            try:
                used = self._spend_provider.spend_since(anchor)
            except CostUnavailableError:
                used = None
        return BudgetStatus(limit_usd=self._limit_usd, used_usd=used, tracking_since=anchor)
