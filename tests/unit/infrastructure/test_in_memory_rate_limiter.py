from datetime import datetime, timedelta, timezone

import pytest

from app.domain.errors import RateLimitExceededError
from app.infrastructure.in_memory_rate_limiter import InMemoryRateLimiter


def test_check_blocks_after_the_failure_limit_is_reached():
    limiter = InMemoryRateLimiter(max_attempts=3, window=timedelta(minutes=15))
    key = "1.2.3.4:dev@example.com"

    for _ in range(3):
        limiter.record_failure(key)

    with pytest.raises(RateLimitExceededError):
        limiter.check(key)


def test_check_allows_attempts_below_the_limit():
    limiter = InMemoryRateLimiter(max_attempts=3, window=timedelta(minutes=15))
    key = "1.2.3.4:dev@example.com"

    limiter.record_failure(key)
    limiter.record_failure(key)

    limiter.check(key)  # 2 < 3: must not raise


def test_failures_expire_after_the_window_passes():
    now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    clock = lambda: now  # noqa: E731
    limiter = InMemoryRateLimiter(max_attempts=3, window=timedelta(minutes=15), clock=clock)
    key = "1.2.3.4:dev@example.com"
    for _ in range(3):
        limiter.record_failure(key)

    now = now + timedelta(minutes=15, seconds=1)

    limiter.check(key)  # window elapsed: clean slate, must not raise


def test_reset_clears_recorded_failures():
    limiter = InMemoryRateLimiter(max_attempts=3, window=timedelta(minutes=15))
    key = "1.2.3.4:dev@example.com"
    for _ in range(3):
        limiter.record_failure(key)

    limiter.reset(key)

    limiter.check(key)  # cleared: must not raise


def test_keys_are_throttled_independently():
    limiter = InMemoryRateLimiter(max_attempts=3, window=timedelta(minutes=15))
    for _ in range(3):
        limiter.record_failure("1.2.3.4:attacker@example.com")

    limiter.check("1.2.3.4:victim@example.com")  # different key: must not raise


def test_exceeded_error_reports_a_positive_retry_after_within_the_window():
    window = timedelta(minutes=15)
    limiter = InMemoryRateLimiter(max_attempts=1, window=window)
    key = "1.2.3.4:dev@example.com"
    limiter.record_failure(key)

    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check(key)

    assert 0 < exc_info.value.retry_after_seconds <= window.total_seconds() + 1
