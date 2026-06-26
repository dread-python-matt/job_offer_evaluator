from datetime import datetime, timezone

from app.application.ports import ModelUsageRepository, ModelUsageSummary
from app.infrastructure.token_accounting_provider_spend_provider import (
    TokenAccountingProviderSpendProvider,
)


class _UsageRepo(ModelUsageRepository):
    def __init__(self, summaries):
        self._summaries = summaries

    def save(self, usage):
        raise NotImplementedError

    def get_summary(self, user_id):
        return self._summaries

    def usage_since(self, user_id, start):
        return self._summaries


_START = datetime(2026, 6, 25, tzinfo=timezone.utc)


def test_sums_only_the_requested_companys_cost():
    repo = _UsageRepo(
        [
            ModelUsageSummary("OpenAI", "gpt-4o", input_tokens=0, output_tokens=0, cost_usd=10.0),
            ModelUsageSummary("Google", "gemini-2.0", input_tokens=0, output_tokens=0, cost_usd=2.0),
        ]
    )

    spend = TokenAccountingProviderSpendProvider(repo)

    assert spend.spend_since("u1", "OpenAI", _START) == 10.0


def test_sums_multiple_models_for_the_same_company():
    repo = _UsageRepo(
        [
            ModelUsageSummary("OpenAI", "gpt-4o", input_tokens=0, output_tokens=0, cost_usd=10.0),
            ModelUsageSummary("OpenAI", "gpt-4o-mini", input_tokens=0, output_tokens=0, cost_usd=0.5),
        ]
    )

    spend = TokenAccountingProviderSpendProvider(repo)

    assert spend.spend_since("u1", "OpenAI", _START) == 10.5


def test_a_company_with_no_recorded_usage_is_zero():
    repo = _UsageRepo(
        [ModelUsageSummary("OpenAI", "gpt-4o", input_tokens=0, output_tokens=0, cost_usd=10.0)]
    )

    spend = TokenAccountingProviderSpendProvider(repo)

    assert spend.spend_since("u1", "Google", _START) == 0.0
