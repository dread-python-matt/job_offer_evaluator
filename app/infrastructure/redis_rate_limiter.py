from datetime import timedelta
from typing import Protocol

from app.application.ports import RateLimiter
from app.domain.errors import RateLimitExceededError


class RedisClient(Protocol):
    """The slice of a redis-py client this limiter uses. Declaring it as a Protocol keeps the
    adapter testable with a fake and avoids a hard import of `redis` in this module."""

    def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...
    def get(self, name: str) -> str | bytes | None: ...
    def ttl(self, name: str) -> int: ...
    def delete(self, name: str) -> int: ...


# Atomic fixed-window increment: INCR the counter and, only on the first hit of a new window,
# set its TTL — both in one server-side step. Redis runs a script atomically, so unlike a
# separate INCR-then-EXPIRE a crash or dropped connection can never leave a counter with no
# expiry (which would never reset and lock that (IP, email) out of login/forgot-password
# forever). Returns the post-increment count.
_INCR_WITH_EXPIRE_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RedisRateLimiter(RateLimiter):
    """Fixed-window attempt counter backed by Redis, so the throttle is shared across every
    worker and instance (unlike the per-process in-memory limiter). The window is enforced by
    Redis key expiry: the first failure sets the TTL, and the count resets when the key
    expires. `check` is read-only; `record_failure` counts; `reset` clears.

    Keys are namespaced so a Redis instance can be shared with other data without collisions.
    """

    def __init__(
        self,
        client: RedisClient,
        max_attempts: int = 5,
        window: timedelta = timedelta(minutes=15),
        key_prefix: str = "ratelimit:",
    ) -> None:
        self._client = client
        self._max_attempts = max_attempts
        self._window_seconds = int(window.total_seconds())
        self._key_prefix = key_prefix

    def check(self, key: str) -> None:
        count = self._client.get(self._namespaced(key))
        if count is not None and int(count) >= self._max_attempts:
            ttl = self._client.ttl(self._namespaced(key))
            # ttl can be -1 (no expiry) or -2 (no key, e.g. it just expired) — treat those as
            # a full window / a clean slate respectively, never a non-positive retry hint.
            retry_after = ttl if ttl > 0 else (self._window_seconds if ttl == -1 else 1)
            raise RateLimitExceededError(retry_after_seconds=max(retry_after, 1))

    def record_failure(self, key: str) -> None:
        # Atomic INCR + first-hit EXPIRE (see _INCR_WITH_EXPIRE_LUA): the counter always gets a
        # TTL in the same step it's created, so it can't get stuck without one and self-clears
        # when the window elapses.
        self._client.eval(
            _INCR_WITH_EXPIRE_LUA, 1, self._namespaced(key), self._window_seconds
        )

    def reset(self, key: str) -> None:
        self._client.delete(self._namespaced(key))

    def _namespaced(self, key: str) -> str:
        return f"{self._key_prefix}{key}"
