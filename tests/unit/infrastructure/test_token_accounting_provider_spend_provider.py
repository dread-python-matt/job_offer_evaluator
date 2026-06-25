from datetime import datetime, timezone

from app.application.ports import (
    ModelPrice,
    ModelPricingRegistry,
    ModelUsageRepository,
    ModelUsageSummary,
)
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


class _Pricing(ModelPricingRegistry):
    def __init__(self, prices):
        self._prices = prices

    def get_price(self, model):
        return self._prices.get(model)


_START = datetime(2026, 6, 25, tzinfo=timezone.utc)


def test_sums_only_the_requested_companys_priced_usage():
    repo = _UsageRepo(
        [
            ModelUsageSummary("OpenAI", "gpt-4o", input_tokens=1_000_000, output_tokens=0),
            ModelUsageSummary("Google", "gemini-2.0", input_tokens=2_000_000, output_tokens=0),
        ]
    )
    pricing = _Pricing(
        {
            "gpt-4o": ModelPrice(input_per_million=10.0, output_per_million=30.0),
            "gemini-2.0": ModelPrice(input_per_million=1.0, output_per_million=2.0),
        }
    )

    spend = TokenAccountingProviderSpendProvider(repo, pricing)

    assert spend.spend_since("u1", "OpenAI", _START) == 10.0


def test_unknown_priced_models_contribute_zero():
    repo = _UsageRepo(
        [ModelUsageSummary("OpenAI", "mystery-model", input_tokens=5_000_000, output_tokens=0)]
    )

    spend = TokenAccountingProviderSpendProvider(repo, _Pricing({}))

    assert spend.spend_since("u1", "OpenAI", _START) == 0.0


def test_counts_both_input_and_output_tokens():
    repo = _UsageRepo(
        [ModelUsageSummary("OpenAI", "gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)]
    )
    pricing = _Pricing({"gpt-4o": ModelPrice(input_per_million=10.0, output_per_million=30.0)})

    spend = TokenAccountingProviderSpendProvider(repo, pricing)

    assert spend.spend_since("u1", "OpenAI", _START) == 40.0
