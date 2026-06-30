from datetime import datetime, timezone

import openai
from openai import OpenAI

from app.application.ports import AdminKeyValidator
from app.domain.errors import InvalidAdminKeyError

# Statuses OpenAI returns when the admin key itself is the problem — a bad/revoked key
# (401), or a valid key lacking the `api.usage.read` scope (403). A 400 covers a malformed
# request/key. Anything else (429/5xx/network) is transient and bubbles, so an outage is
# never misreported as a bad key.
_KEY_REJECTION_STATUSES = frozenset({400, 401, 403})


class OpenAIAdminKeyValidator(AdminKeyValidator):
    """Validates an OpenAI admin key by making one read-only call to the organization costs
    endpoint — the same endpoint the spend readout uses, so a key that passes here can
    actually power it. The call reads cost metadata only (no tokens billed)."""

    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout

    def validate(self, key: str) -> None:
        # Admin/organization endpoints authenticate with `admin_api_key`, NOT `api_key`. With
        # `api_key` the SDK can't resolve auth for these routes and raises a TypeError at
        # request-build time (not an OpenAIError), which would bubble as a 500 and make every
        # save fail. Passing `admin_api_key` makes a bad key fail cleanly as a 401/403 instead.
        client = OpenAI(admin_api_key=key, timeout=self._timeout)
        start_of_today = int(
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        try:
            client.admin.organization.usage.costs(
                start_time=start_of_today, bucket_width="1d"
            )
        except openai.OpenAIError as exc:
            if getattr(exc, "status_code", None) in _KEY_REJECTION_STATUSES:
                raise InvalidAdminKeyError() from exc
            raise
