from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import openai
import pytest

from app.domain.errors import CostUnavailableError
from app.infrastructure.openai_spend_provider import OpenAISpendProvider

START = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _bucket(amounts: list[float]):
    return SimpleNamespace(
        results=[SimpleNamespace(amount=SimpleNamespace(value=v, currency="usd")) for v in amounts]
    )


def test_sums_spend_across_all_buckets():
    with patch("app.infrastructure.openai_spend_provider.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.return_value = SimpleNamespace(
            data=[_bucket([1.50, 0.75]), _bucket([0.25])]
        )
        provider = OpenAISpendProvider(api_key="test-key")

        assert provider.spend_since(START) == 2.50


def test_returns_zero_when_no_usage():
    with patch("app.infrastructure.openai_spend_provider.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.return_value = SimpleNamespace(data=[])
        provider = OpenAISpendProvider(api_key="test-key")

        assert provider.spend_since(START) == 0.0


def test_queries_from_the_given_start_instant():
    captured = {}

    def fake_costs(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(data=[])

    with patch("app.infrastructure.openai_spend_provider.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.side_effect = fake_costs
        OpenAISpendProvider(api_key="test-key").spend_since(START)

    assert captured["start_time"] == int(START.timestamp())


def test_translates_openai_error_to_cost_unavailable():
    with patch("app.infrastructure.openai_spend_provider.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.side_effect = openai.PermissionDeniedError(
            message="Missing scopes: api.usage.read",
            response=SimpleNamespace(status_code=403, request=None, headers={}),
            body=None,
        )
        provider = OpenAISpendProvider(api_key="test-key")

        with pytest.raises(CostUnavailableError):
            provider.spend_since(START)
