from datetime import datetime, timezone

from app.application.ports import SpendProvider
from app.application.use_cases import GetOrgSpendUseCase, OrgSpend
from app.domain.errors import CostUnavailableError

_NOON = datetime(2026, 6, 25, 12, 30, tzinfo=timezone.utc)
# Spend is reported month-to-date (UTC) to mirror OpenAI's usage page "this month" total.
_START_OF_MONTH = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)


class _FixedSpend(SpendProvider):
    def __init__(self, amount: float):
        self.amount = amount
        self.asked: datetime | None = None

    def spend_since(self, start):
        self.asked = start
        return self.amount


class _UnavailableSpend(SpendProvider):
    def spend_since(self, start):
        raise CostUnavailableError("usage API unauthorized")


def test_returns_none_when_no_spend_provider_is_configured():
    assert GetOrgSpendUseCase(None, clock=lambda: _NOON).execute() is None


def test_reports_actual_spend_since_the_start_of_the_utc_month():
    spend = _FixedSpend(4.20)

    result = GetOrgSpendUseCase(spend, clock=lambda: _NOON).execute()

    assert result == OrgSpend(spend_usd=4.20, since=_START_OF_MONTH)
    assert spend.asked == _START_OF_MONTH


def test_returns_none_when_the_spend_figure_is_unavailable():
    assert (
        GetOrgSpendUseCase(_UnavailableSpend(), clock=lambda: _NOON).execute() is None
    )
