from dataclasses import replace
from datetime import datetime

from app.application.ports import (
    ModelPricingRegistry,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageSummary,
)
from app.application.usage_pricing import UsagePricer


class PricingModelUsageRepository(ModelUsageRepository):
    """Decorator that snapshots each usage record's USD cost at write time.

    Pricing is applied once, when a row is saved, and frozen into `cost_usd` — so a later
    price change never rewrites historical spend, and spend reads sum a stored number instead
    of re-pricing tokens on every read. Reads delegate unchanged to the wrapped repository."""

    def __init__(self, inner: ModelUsageRepository, pricing: ModelPricingRegistry) -> None:
        self._inner = inner
        self._pricer = UsagePricer(pricing)

    def save(self, usage: ModelUsage) -> None:
        cost = self._pricer.cost_of(
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
        )
        self._inner.save(replace(usage, cost_usd=cost))

    def get_summary(self, user_id: str) -> list[ModelUsageSummary]:
        return self._inner.get_summary(user_id)

    def usage_since(self, user_id: str, start: datetime) -> list[ModelUsageSummary]:
        return self._inner.usage_since(user_id, start)

    def count_requests_since(self, user_id: str, company: str, start: datetime) -> int:
        return self._inner.count_requests_since(user_id, company, start)
