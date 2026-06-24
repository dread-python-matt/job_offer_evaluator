from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BudgetSettings:
    """The persisted budget configuration: a spend limit and the anchor from which
    usage is accumulated. `tracking_since` only changes on an explicit reset, so
    usage never resets automatically."""

    limit_usd: float
    tracking_since: datetime


@dataclass(frozen=True)
class BudgetStatus:
    """A point-in-time view of the budget: the limit, the spend accrued since
    `tracking_since`, and whether the limit is reached. `used_usd` is None when the
    spend figure can't be read (e.g. no admin key / usage API unavailable)."""

    limit_usd: float
    used_usd: float | None
    tracking_since: datetime

    @property
    def exceeded(self) -> bool:
        return self.used_usd is not None and self.used_usd >= self.limit_usd
