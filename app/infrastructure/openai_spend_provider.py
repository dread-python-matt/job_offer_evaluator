from datetime import datetime

import openai
from openai import OpenAI

from app.application.ports import SpendProvider
from app.domain.errors import CostUnavailableError


class OpenAISpendProvider(SpendProvider):
    """Reads actual money spent via OpenAI's organization costs admin API. Requires an
    admin key with the `api.usage.read` scope; failures surface as CostUnavailableError
    so callers can degrade gracefully."""

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def spend_since(self, start: datetime) -> float:
        client = OpenAI(api_key=self._api_key, timeout=self._timeout)
        start_time = int(start.timestamp())
        total = 0.0
        page: str | None = None
        try:
            # The costs endpoint only supports daily buckets. A single day is usually one
            # bucket on one page, but follow `next_page` until exhausted so a multi-page
            # result (e.g. grouped line items) is never silently truncated.
            while True:
                extra = {"page": page} if page else {}
                response = client.admin.organization.usage.costs(
                    start_time=start_time, bucket_width="1d", **extra
                )
                total += sum(
                    result.amount.value
                    for bucket in response.data
                    for result in bucket.results
                )
                if not getattr(response, "has_more", False):
                    break
                page = getattr(response, "next_page", None)
                if not page:
                    break
        except openai.OpenAIError as exc:
            raise CostUnavailableError(str(exc)) from exc
        return total
