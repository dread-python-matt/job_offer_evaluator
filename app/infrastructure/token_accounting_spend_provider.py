from datetime import datetime

from app.application.ports import ModelPricingRegistry, ModelUsageRepository, UserSpendProvider


class TokenAccountingSpendProvider(UserSpendProvider):
    """Per-user spend derived from this app's own token accounting: sums the user's
    recorded model usage since `start` and prices it with the pricing registry. Usage on
    models with no known price is ignored (contributes $0), so the estimate is a lower
    bound — acceptable for a best-effort budget guard."""

    def __init__(
        self, usage_repository: ModelUsageRepository, pricing: ModelPricingRegistry
    ) -> None:
        self._usage_repository = usage_repository
        self._pricing = pricing

    def spend_since(self, user_id: str, start: datetime) -> float:
        total = 0.0
        for summary in self._usage_repository.usage_since(user_id, start):
            price = self._pricing.get_price(summary.model)
            if price is None:
                continue
            total += summary.input_tokens / 1_000_000 * price.input_per_million
            total += summary.output_tokens / 1_000_000 * price.output_per_million
        return total
