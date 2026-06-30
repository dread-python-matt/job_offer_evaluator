from datetime import datetime, timedelta, timezone

import pytest

from app.domain.errors import RateLimitExceededError
from app.infrastructure.redis_rate_limiter import RedisRateLimiter

_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


class FakeRedis:
    """In-memory stand-in modelling EVAL (the limiter's atomic INCR+EXPIRE script) / GET / TTL /
    DEL with a controllable clock — enough to exercise the fixed-window limiter without a real
    Redis. Being single-threaded, its `eval` is naturally atomic, like Redis's."""

    def __init__(self, clock) -> None:
        self._clock = clock
        self._store: dict[str, int] = {}
        self._expire_at: dict[str, datetime] = {}

    def _evict_if_expired(self, name: str) -> None:
        exp = self._expire_at.get(name)
        if exp is not None and self._clock() >= exp:
            self._store.pop(name, None)
            self._expire_at.pop(name, None)

    def _incr(self, name: str) -> int:
        self._evict_if_expired(name)
        self._store[name] = self._store.get(name, 0) + 1
        return self._store[name]

    def _expire(self, name: str, seconds: int) -> bool:
        self._evict_if_expired(name)
        if name not in self._store:
            return False
        self._expire_at[name] = self._clock() + timedelta(seconds=seconds)
        return True

    def eval(self, script: str, numkeys: int, *keys_and_args):
        # Models _INCR_WITH_EXPIRE_LUA: INCR, then EXPIRE only on the first hit of a new window.
        name = keys_and_args[0]
        seconds = int(keys_and_args[1])
        count = self._incr(name)
        if count == 1:
            self._expire(name, seconds)
        return count

    def get(self, name: str):
        self._evict_if_expired(name)
        return self._store.get(name)

    def ttl(self, name: str) -> int:
        self._evict_if_expired(name)
        if name not in self._store:
            return -2
        exp = self._expire_at.get(name)
        if exp is None:
            return -1
        return int((exp - self._clock()).total_seconds())

    def delete(self, name: str) -> int:
        existed = name in self._store
        self._store.pop(name, None)
        self._expire_at.pop(name, None)
        return 1 if existed else 0


def _limiter(clock, max_attempts=3, window=timedelta(minutes=15)) -> RedisRateLimiter:
    return RedisRateLimiter(FakeRedis(clock), max_attempts=max_attempts, window=window)


def test_check_blocks_after_the_failure_limit_is_reached():
    limiter = _limiter(lambda: _NOW)
    key = "1.2.3.4:dev@example.com"
    for _ in range(3):
        limiter.record_failure(key)

    with pytest.raises(RateLimitExceededError):
        limiter.check(key)


def test_check_allows_attempts_below_the_limit():
    limiter = _limiter(lambda: _NOW)
    key = "1.2.3.4:dev@example.com"

    limiter.record_failure(key)
    limiter.record_failure(key)

    limiter.check(key)  # 2 < 3: must not raise


def test_failures_expire_after_the_window_passes():
    now = [_NOW]
    limiter = _limiter(lambda: now[0])
    key = "1.2.3.4:dev@example.com"
    for _ in range(3):
        limiter.record_failure(key)

    now[0] = _NOW + timedelta(minutes=15, seconds=1)

    limiter.check(key)  # window elapsed (Redis key expired): clean slate, must not raise


def test_reset_clears_recorded_failures():
    limiter = _limiter(lambda: _NOW)
    key = "1.2.3.4:dev@example.com"
    for _ in range(3):
        limiter.record_failure(key)

    limiter.reset(key)

    limiter.check(key)  # cleared: must not raise


def test_keys_are_throttled_independently():
    limiter = _limiter(lambda: _NOW)
    for _ in range(3):
        limiter.record_failure("1.2.3.4:attacker@example.com")

    limiter.check("1.2.3.4:victim@example.com")  # different key: must not raise


def test_exceeded_error_reports_a_positive_retry_after_within_the_window():
    window = timedelta(minutes=15)
    limiter = _limiter(lambda: _NOW, max_attempts=1, window=window)
    key = "1.2.3.4:dev@example.com"
    limiter.record_failure(key)

    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check(key)

    assert 0 < exc_info.value.retry_after_seconds <= window.total_seconds() + 1


def test_keys_are_namespaced_so_a_redis_instance_can_be_shared():
    fake = FakeRedis(lambda: _NOW)
    limiter = RedisRateLimiter(fake, max_attempts=3, key_prefix="ratelimit:")

    limiter.record_failure("login:1.2.3.4:dev@example.com")

    assert "ratelimit:login:1.2.3.4:dev@example.com" in fake._store


def test_first_failure_sets_an_expiry_atomically():
    # The counter must always get a TTL in the same step it's created, so it can never get
    # stuck without one (which would permanently lock the key out).
    fake = FakeRedis(lambda: _NOW)
    limiter = RedisRateLimiter(fake, max_attempts=3, window=timedelta(minutes=15))
    key = "1.2.3.4:dev@example.com"

    limiter.record_failure(key)

    assert fake.ttl("ratelimit:" + key) > 0
