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


@dataclass(frozen=True)
class DailyRequestStatus:
    """A point-in-time view of a provider key's *daily request* budget (a free-tier-friendly
    alternative to the USD budget): how many requests the user has made today, the effective
    daily cap, and the free-tier default the cap derives from. Unlike spend, the count comes
    from this app's own records, so it is always known (never None).

    `limit` is the effective cap actually enforced — the user's override when set, otherwise
    `default_limit` (the model's free-tier requests-per-day). `default_limit` is None when the
    model's RPD is unknown (then a status is only produced if the user set an override)."""

    used: int
    limit: int
    default_limit: int | None

    @property
    def exceeded(self) -> bool:
        return self.used >= self.limit
