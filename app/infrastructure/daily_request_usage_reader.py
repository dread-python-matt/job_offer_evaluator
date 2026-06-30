from collections.abc import Callable
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.application.ports import (
    ApiKeyRepository,
    DailyRequestUsageReader,
    ModelLimitsRegistry,
    ModelUsageRepository,
)
from app.domain.api_providers import provider_for_company
from app.domain.budget import DailyRequestStatus
from app.infrastructure.llm_utils import company_from_model

# Gemini's free-tier requests-per-day quota resets at midnight US/Pacific, so the daily count
# is taken from that boundary to line up with the provider's own reset.
PACIFIC = ZoneInfo("America/Los_Angeles")


def start_of_day(now_utc: datetime, tz: tzinfo) -> datetime:
    """The UTC instant of the most recent midnight in `tz` — the start of 'today' for the
    per-day request count."""
    local = now_utc.astimezone(tz)
    midnight_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TokenAccountingDailyRequestUsageReader(DailyRequestUsageReader):
    """Derives a user's per-day request budget for a model from this app's own usage records:
    counts the rows recorded for the model's provider since the daily reset, against the
    effective cap (the key's override, else the model's free-tier requests-per-day from the
    limits registry).

    Returns None — i.e. 'no daily cap to enforce' — when the model's provider isn't keyable,
    the user has no key for it, or the model's RPD is unknown *and* no override is set. The AI
    match gate treats None as ungated (fail-open), so an unknown model is never wrongly blocked.
    """

    def __init__(
        self,
        api_keys: ApiKeyRepository,
        usage_repository: ModelUsageRepository,
        limits_registry: ModelLimitsRegistry,
        clock: Callable[[], datetime] = _utc_now,
        tz: tzinfo = PACIFIC,
    ) -> None:
        self._api_keys = api_keys
        self._usage_repository = usage_repository
        self._limits_registry = limits_registry
        self._clock = clock
        self._tz = tz

    def status_for(self, user_id: str, model: str) -> DailyRequestStatus | None:
        company = company_from_model(model)
        provider = provider_for_company(company)
        if provider is None:
            return None
        key = self._api_keys.get(user_id, provider)
        if key is None:
            return None
        limits = self._limits_registry.get_limits(model)
        default_limit = limits.rpd if limits is not None else None
        effective = key.daily_request_limit if key.daily_request_limit is not None else default_limit
        if effective is None:
            return None  # unknown model and no override → nothing to enforce
        start = start_of_day(self._clock(), self._tz)
        used = self._usage_repository.count_requests_since(user_id, company, start)
        return DailyRequestStatus(used=used, limit=effective, default_limit=default_limit)
