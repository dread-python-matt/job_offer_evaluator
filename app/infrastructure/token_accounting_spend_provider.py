from datetime import datetime

from app.application.ports import ModelPricingRegistry, ModelUsageRepository, UserSpendProvider
from app.application.usage_pricing import UsagePricer


class TokenAccountingSpendProvider(UserSpendProvider):
    """Per-user spend derived from this app's own token accounting: sums the user's
    recorded model usage since `start` and prices it with the pricing registry. Usage on
    models with no known price is ignored (contributes $0, and is logged once), so the
    estimate is a lower bound — acceptable for a best-effort budget guard."""

    def __init__(
        self, usage_repository: ModelUsageRepository, pricing: ModelPricingRegistry
    ) -> None:
        self._usage_repository = usage_repository
        self._pricer = UsagePricer(pricing)

    def spend_since(self, user_id: str, start: datetime) -> float:
        return sum(
            self._pricer.cost_of(s.model, s.input_tokens, s.output_tokens)
            for s in self._usage_repository.usage_since(user_id, start)
        )
