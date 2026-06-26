from datetime import datetime, timezone

from app.application.ports import (
    ModelPrice,
    ModelPricingRegistry,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageSummary,
)
from app.infrastructure.pricing_model_usage_repository import PricingModelUsageRepository


class _RecordingRepo(ModelUsageRepository):
    def __init__(self) -> None:
        self.saved: list[ModelUsage] = []
        self.summary_calls: list[str] = []
        self.since_calls: list[tuple[str, datetime]] = []

    def save(self, usage: ModelUsage) -> None:
        self.saved.append(usage)

    def get_summary(self, user_id: str) -> list[ModelUsageSummary]:
        self.summary_calls.append(user_id)
        return [ModelUsageSummary("OpenAI", "gpt-4o", 1, 2, cost_usd=3.0)]

    def usage_since(self, user_id: str, start: datetime) -> list[ModelUsageSummary]:
        self.since_calls.append((user_id, start))
        return [ModelUsageSummary("OpenAI", "gpt-4o", 1, 2, cost_usd=3.0)]


class _Pricing(ModelPricingRegistry):
    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices

    def get_price(self, model: str) -> ModelPrice | None:
        return self._prices.get(model)


_PRICING = _Pricing(
    {"gpt-4o": ModelPrice(input_per_million=2.50, output_per_million=10.0)}
)


def _usage(model: str, input_tokens: int, output_tokens: int) -> ModelUsage:
    return ModelUsage(
        label="scoring",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        company="OpenAI",
        user_id="u1",
    )


def test_save_snapshots_the_priced_cost_onto_the_row():
    inner = _RecordingRepo()
    repo = PricingModelUsageRepository(inner, _PRICING)

    repo.save(_usage("gpt-4o", input_tokens=1_000_000, output_tokens=500_000))

    # 1M input * $2.50 + 0.5M output * $10.00 = 2.50 + 5.00
    assert inner.saved[0].cost_usd == 7.50


def test_save_preserves_every_other_field():
    inner = _RecordingRepo()
    repo = PricingModelUsageRepository(inner, _PRICING)

    original = _usage("gpt-4o", input_tokens=10, output_tokens=20)
    repo.save(original)

    saved = inner.saved[0]
    assert (saved.label, saved.model, saved.company, saved.user_id) == (
        "scoring",
        "gpt-4o",
        "OpenAI",
        "u1",
    )
    assert (saved.input_tokens, saved.output_tokens) == (10, 20)


def test_unpriced_model_is_snapshotted_as_zero():
    inner = _RecordingRepo()
    repo = PricingModelUsageRepository(inner, _PRICING)

    repo.save(_usage("mystery-model", input_tokens=1_000_000, output_tokens=1_000_000))

    assert inner.saved[0].cost_usd == 0.0


def test_reads_delegate_to_the_wrapped_repository():
    inner = _RecordingRepo()
    repo = PricingModelUsageRepository(inner, _PRICING)
    start = datetime(2026, 6, 26, tzinfo=timezone.utc)

    assert repo.get_summary("u1") == inner.get_summary("u1")
    assert repo.usage_since("u1", start) == inner.usage_since("u1", start)
    assert inner.summary_calls == ["u1", "u1"]
    assert inner.since_calls == [("u1", start), ("u1", start)]
