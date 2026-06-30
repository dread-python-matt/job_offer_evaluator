from datetime import datetime, timezone

from app.application.ports import (
    ApiKeyRecord,
    ModelLimits,
    ModelLimitsRegistry,
    ModelUsageRepository,
)
from app.infrastructure.daily_request_usage_reader import (
    TokenAccountingDailyRequestUsageReader,
    start_of_day,
)
from tests.fakes import InMemoryApiKeyRepository

_NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


class _FakeLimitsRegistry(ModelLimitsRegistry):
    def __init__(self, limits: dict[str, ModelLimits] | None = None) -> None:
        self._limits = limits or {}

    def get_limits(self, model):
        return self._limits.get(model)


class _RecordingUsageRepo(ModelUsageRepository):
    """Returns a fixed request count and records the (user_id, company, start) it was asked
    about, so tests can assert the reader scopes the count to the model's company since the
    Pacific daily reset."""

    def __init__(self, count: int) -> None:
        self._count = count
        self.asked: tuple | None = None

    def save(self, usage):
        raise NotImplementedError

    def get_summary(self, user_id):
        return []

    def usage_since(self, user_id, start):
        return []

    def count_requests_since(self, user_id, company, start):
        self.asked = (user_id, company, start)
        return self._count


def _key(provider: str, daily_request_limit: int | None = None) -> ApiKeyRecord:
    return ApiKeyRecord(
        user_id="u1",
        api_provider=provider,
        key_ciphertext="x",
        key_hint="x",
        limit_usd=10.0,
        tracking_since=_NOW,
        created_at=_NOW,
        daily_request_limit=daily_request_limit,
    )


def _reader(
    keys: InMemoryApiKeyRepository,
    usage: ModelUsageRepository,
    limits: dict[str, ModelLimits] | None = None,
    now: datetime = _NOW,
) -> TokenAccountingDailyRequestUsageReader:
    return TokenAccountingDailyRequestUsageReader(
        keys,
        usage,
        _FakeLimitsRegistry(limits),
        clock=lambda: now,
    )


# --- start_of_day (the Pacific daily-reset boundary) ---


def test_start_of_day_is_utc_instant_of_pacific_midnight_in_summer():
    # Late June is PDT (UTC-7). 05:00 UTC is still 22:00 the previous day in Pacific.
    from zoneinfo import ZoneInfo

    start = start_of_day(
        datetime(2026, 6, 30, 5, 0, tzinfo=timezone.utc),
        ZoneInfo("America/Los_Angeles"),
    )

    assert start == datetime(2026, 6, 29, 7, 0, tzinfo=timezone.utc)


def test_start_of_day_is_utc_instant_of_pacific_midnight_in_winter():
    # Mid-January is PST (UTC-8).
    from zoneinfo import ZoneInfo

    start = start_of_day(
        datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc),
        ZoneInfo("America/Los_Angeles"),
    )

    assert start == datetime(2026, 1, 14, 8, 0, tzinfo=timezone.utc)


# --- status_for ---


def test_status_uses_model_rpd_default_and_counts_since_pacific_midnight():
    keys = InMemoryApiKeyRepository()
    keys.add(_key("google"))
    usage = _RecordingUsageRepo(123)
    reader = _reader(
        keys,
        usage,
        {"gemini-2.5-flash": ModelLimits(rpm=10, tpm=250_000, rpd=500)},
        now=datetime(2026, 6, 30, 5, 0, tzinfo=timezone.utc),
    )

    status = reader.status_for("u1", "gemini-2.5-flash")

    assert status is not None
    assert status.used == 123
    assert status.limit == 500
    assert status.default_limit == 500
    assert status.exceeded is False
    # Counted for the model's company since the most recent Pacific midnight.
    assert usage.asked == (
        "u1",
        "Google",
        datetime(2026, 6, 29, 7, 0, tzinfo=timezone.utc),
    )


def test_status_uses_user_override_over_model_default():
    keys = InMemoryApiKeyRepository()
    keys.add(_key("google", daily_request_limit=50))
    reader = _reader(
        keys,
        _RecordingUsageRepo(50),
        {"gemini-2.5-flash": ModelLimits(rpm=10, tpm=250_000, rpd=500)},
    )

    status = reader.status_for("u1", "gemini-2.5-flash")

    assert status is not None
    assert status.limit == 50  # the override, not the model's 500
    assert (
        status.default_limit == 500
    )  # still surfaces the free-tier default for display
    assert status.exceeded is True  # 50 of 50


def test_status_is_none_when_provider_is_not_keyable():
    keys = InMemoryApiKeyRepository()
    reader = _reader(keys, _RecordingUsageRepo(0))

    # Anthropic models have no user-keyable provider in this app.
    assert reader.status_for("u1", "claude-3-5-sonnet") is None


def test_status_is_none_when_user_has_no_key_for_the_provider():
    keys = InMemoryApiKeyRepository()  # no Google key
    reader = _reader(
        keys,
        _RecordingUsageRepo(0),
        {"gemini-2.5-flash": ModelLimits(rpm=10, tpm=250_000, rpd=500)},
    )

    assert reader.status_for("u1", "gemini-2.5-flash") is None


def test_status_is_none_when_model_rpd_unknown_and_no_override():
    keys = InMemoryApiKeyRepository()
    keys.add(_key("google"))  # no override

    reader = _reader(keys, _RecordingUsageRepo(0), limits={})  # unknown model

    assert reader.status_for("u1", "gemini-9.9-experimental") is None


def test_status_uses_override_even_when_model_rpd_unknown():
    keys = InMemoryApiKeyRepository()
    keys.add(_key("google", daily_request_limit=20))

    reader = _reader(keys, _RecordingUsageRepo(5), limits={})  # unknown model

    status = reader.status_for("u1", "gemini-9.9-experimental")

    assert status is not None
    assert status.used == 5
    assert status.limit == 20
    assert status.default_limit is None  # no known free-tier default
