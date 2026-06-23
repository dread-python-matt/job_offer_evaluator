from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.application.ports import ExternalUsageProvider, ModelUsageSummary
from app.infrastructure.llm_utils import company_from_model


class OpenAIExternalUsageProvider(ExternalUsageProvider):
    def __init__(self, client: Any) -> None:
        self._client = client

    def get_today_usage(self) -> list[ModelUsageSummary]:
        today_start = int(
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        response = self._client.organization.usage.completions.list(start_time=today_start)

        totals: dict[str, dict[str, int]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0}
        )
        for bucket in response.data:
            for result in bucket.results:
                if not result.model:
                    continue
                totals[result.model]["input_tokens"] += result.input_tokens
                totals[result.model]["output_tokens"] += result.output_tokens

        return [
            ModelUsageSummary(
                company=company_from_model(model),
                model=model,
                input_tokens=data["input_tokens"],
                output_tokens=data["output_tokens"],
            )
            for model, data in totals.items()
        ]
