from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import openai

from app.application.ports import ExternalUsageProvider, ModelUsageSummary
from app.domain.errors import CostUnavailableError
from app.infrastructure.llm_utils import company_from_model


class OpenAIExternalUsageProvider(ExternalUsageProvider):
    """Reads the organization's *actual* token usage for the current UTC day from OpenAI's
    admin usage API (`organization.usage.completions`). Requires an admin key with the
    `api.usage.read` scope. The figure is org-wide and cannot be attributed per user.
    Failures surface as CostUnavailableError so callers can degrade gracefully."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_today_usage(self) -> list[ModelUsageSummary]:
        today_start = int(
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        totals: dict[str, dict[str, int]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0}
        )
        try:
            for bucket in self._iter_buckets(today_start):
                for result in bucket.results:
                    if not result.model:
                        continue
                    totals[result.model]["input_tokens"] += result.input_tokens
                    totals[result.model]["output_tokens"] += result.output_tokens
        except openai.OpenAIError as exc:
            raise CostUnavailableError(str(exc)) from exc

        return [
            ModelUsageSummary(
                company=company_from_model(model),
                model=model,
                input_tokens=data["input_tokens"],
                output_tokens=data["output_tokens"],
            )
            for model, data in totals.items()
        ]

    def _iter_buckets(self, start_time: int) -> Iterator[Any]:
        # `group_by=["model"]` is required for a per-model breakdown — without it the API
        # returns a single aggregate row with model=None, which we'd drop and report nothing.
        # bucket_width="1d" keeps "today" to one bucket per page; results can still span pages,
        # so follow `next_page` until exhausted (stopping at the first page would undercount).
        page: str | None = None
        while True:
            extra = {"page": page} if page else {}
            response = self._client.admin.organization.usage.completions(
                start_time=start_time,
                bucket_width="1d",
                group_by=["model"],
                **extra,
            )
            yield from response.data
            if not getattr(response, "has_more", False):
                return
            page = getattr(response, "next_page", None)
            if not page:
                return
