from datetime import datetime

import openai
from openai import OpenAI

from app.application.ports import SpendProvider
from app.domain.errors import CostUnavailableError


class OpenAISpendProvider(SpendProvider):
    """Reads actual money spent via OpenAI's organization costs admin API. Requires an
    admin key with the `api.usage.read` scope; failures surface as CostUnavailableError
    so callers can degrade gracefully."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def spend_since(self, start: datetime) -> float:
        client = OpenAI(api_key=self._api_key)
        try:
            response = client.admin.organization.usage.costs(start_time=int(start.timestamp()))
        except openai.OpenAIError as exc:
            raise CostUnavailableError(str(exc)) from exc
        return sum(
            result.amount.value
            for bucket in response.data
            for result in bucket.results
        )
