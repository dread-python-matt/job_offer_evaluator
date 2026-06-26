from datetime import datetime

from app.application.ports import (
    ModelPricingRegistry,
    ModelUsageRepository,
    UserProviderSpendProvider,
)
from app.application.usage_pricing import UsagePricer


class TokenAccountingProviderSpendProvider(UserProviderSpendProvider):
    """Per-user, per-provider spend derived from this app's own token accounting: sums the
    user's recorded usage on a single company's models since `start` and prices it with the
    pricing registry. Usage on models with no known price contributes $0 (logged once), so
    the figure is a lower-bound estimate — acceptable for a best-effort per-key budget."""

    def __init__(
        self, usage_repository: ModelUsageRepository, pricing: ModelPricingRegistry
    ) -> None:
        self._usage_repository = usage_repository
        self._pricer = UsagePricer(pricing)

    def spend_since(self, user_id: str, company: str, start: datetime) -> float:
        return sum(
            self._pricer.cost_of(s.model, s.input_tokens, s.output_tokens)
            for s in self._usage_repository.usage_since(user_id, start)
            if s.company == company
        )
