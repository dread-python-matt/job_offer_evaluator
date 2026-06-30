from types import SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest

from app.domain.errors import CostUnavailableError
from app.infrastructure.openai_usage_provider import OpenAIExternalUsageProvider


def _make_result(model: str, input_tokens: int, output_tokens: int):
    return SimpleNamespace(model=model, input_tokens=input_tokens, output_tokens=output_tokens)


def _make_bucket(*results):
    return SimpleNamespace(results=list(results))


def _make_client(buckets: list) -> MagicMock:
    client = MagicMock()
    client.admin.organization.usage.completions.return_value = SimpleNamespace(data=buckets)
    return client


def test_returns_aggregated_usage_per_model():
    client = _make_client([
        _make_bucket(_make_result("gpt-4o", 1000, 200)),
        _make_bucket(_make_result("gpt-4o", 500, 100)),
    ])
    provider = OpenAIExternalUsageProvider(client)

    summaries = provider.get_today_usage()

    assert len(summaries) == 1
    assert summaries[0].model == "gpt-4o"
    assert summaries[0].input_tokens == 1500
    assert summaries[0].output_tokens == 300
    assert summaries[0].company == "OpenAI"


def test_returns_separate_entries_for_different_models():
    client = _make_client([
        _make_bucket(
            _make_result("gpt-4o", 1000, 200),
            _make_result("gpt-4o-mini", 500, 100),
        ),
    ])
    provider = OpenAIExternalUsageProvider(client)

    summaries = provider.get_today_usage()

    models = {s.model for s in summaries}
    assert models == {"gpt-4o", "gpt-4o-mini"}


def test_returns_empty_when_no_usage_data():
    client = _make_client([])
    provider = OpenAIExternalUsageProvider(client)

    assert provider.get_today_usage() == []


def test_skips_results_with_none_model():
    client = _make_client([
        _make_bucket(
            _make_result(None, 100, 50),
            _make_result("gpt-4o", 200, 80),
        ),
    ])
    provider = OpenAIExternalUsageProvider(client)

    summaries = provider.get_today_usage()

    assert len(summaries) == 1
    assert summaries[0].model == "gpt-4o"


def test_calls_api_with_todays_start_time():
    client = _make_client([])
    provider = OpenAIExternalUsageProvider(client)

    provider.get_today_usage()

    call_kwargs = client.admin.organization.usage.completions.call_args.kwargs
    assert "start_time" in call_kwargs
    assert call_kwargs["start_time"] > 0


def test_requests_a_per_model_breakdown_in_daily_buckets():
    # Without group_by=["model"] the real API returns one aggregate row with model=None
    # (which gets dropped), reporting zero usage; bucket_width="1d" keeps today to one bucket.
    client = _make_client([])
    OpenAIExternalUsageProvider(client).get_today_usage()

    kwargs = client.admin.organization.usage.completions.call_args.kwargs
    assert kwargs["group_by"] == ["model"]
    assert kwargs["bucket_width"] == "1d"


def test_paginates_until_no_more_pages():
    client = MagicMock()
    page1 = SimpleNamespace(
        data=[_make_bucket(_make_result("gpt-4o", 1000, 200))],
        has_more=True,
        next_page="cursor-2",
    )
    page2 = SimpleNamespace(
        data=[_make_bucket(_make_result("gpt-4o", 500, 100))],
        has_more=False,
        next_page=None,
    )
    client.admin.organization.usage.completions.side_effect = [page1, page2]
    provider = OpenAIExternalUsageProvider(client)

    summaries = provider.get_today_usage()

    assert len(summaries) == 1
    assert (summaries[0].input_tokens, summaries[0].output_tokens) == (1500, 300)
    second_call = client.admin.organization.usage.completions.call_args_list[1]
    assert second_call.kwargs["page"] == "cursor-2"


def test_translates_openai_error_to_cost_unavailable():
    client = MagicMock()
    client.admin.organization.usage.completions.side_effect = openai.PermissionDeniedError(
        message="Missing scopes: api.usage.read",
        response=SimpleNamespace(status_code=403, request=None, headers={}),
        body=None,
    )
    provider = OpenAIExternalUsageProvider(client)

    with pytest.raises(CostUnavailableError):
        provider.get_today_usage()
