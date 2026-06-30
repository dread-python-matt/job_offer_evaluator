from datetime import datetime, timezone

from app.application.ports import ExternalUsageProvider, ModelUsageSummary
from app.application.use_cases import GetOrgUsageUseCase, OrgUsage
from app.domain.errors import CostUnavailableError

_NOON = datetime(2026, 6, 25, 12, 30, tzinfo=timezone.utc)
_START_OF_DAY = datetime(2026, 6, 25, 0, 0, tzinfo=timezone.utc)

_USAGE = [
    ModelUsageSummary(
        company="OpenAI", model="gpt-4o", input_tokens=1500, output_tokens=300
    )
]


class _FixedUsage(ExternalUsageProvider):
    def __init__(self, usage):
        self.usage = usage

    def get_today_usage(self):
        return self.usage


class _UnavailableUsage(ExternalUsageProvider):
    def get_today_usage(self):
        raise CostUnavailableError("usage API unauthorized")


def test_returns_none_when_no_usage_provider_is_configured():
    assert GetOrgUsageUseCase(None, clock=lambda: _NOON).execute() is None


def test_reports_actual_usage_since_the_start_of_the_utc_day():
    result = GetOrgUsageUseCase(_FixedUsage(_USAGE), clock=lambda: _NOON).execute()

    assert result == OrgUsage(models=_USAGE, since=_START_OF_DAY)


def test_returns_none_when_the_usage_figure_is_unavailable():
    assert (
        GetOrgUsageUseCase(_UnavailableUsage(), clock=lambda: _NOON).execute() is None
    )
