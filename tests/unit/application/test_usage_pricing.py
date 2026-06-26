import logging

from app.application.ports import ModelPrice, ModelPricingRegistry
from app.application.usage_pricing import UsagePricer


class _Pricing(ModelPricingRegistry):
    def __init__(self, prices):
        self._prices = prices

    def get_price(self, model):
        return self._prices.get(model)


def test_cost_of_prices_both_input_and_output_tokens():
    pricer = UsagePricer(
        _Pricing({"gpt-4o": ModelPrice(input_per_million=10.0, output_per_million=30.0)})
    )

    assert pricer.cost_of("gpt-4o", 1_000_000, 1_000_000) == 40.0


def test_an_unpriced_model_costs_zero():
    pricer = UsagePricer(_Pricing({}))

    assert pricer.cost_of("mystery-model", 5_000_000, 1_000_000) == 0.0


def test_an_unpriced_model_is_warned_once_not_on_every_call(caplog):
    # A $0 for an unpriced model silently bypasses the budget, so it must be surfaced —
    # but only once per model, or a hot read path would flood the logs.
    pricer = UsagePricer(_Pricing({}))

    with caplog.at_level(logging.WARNING):
        pricer.cost_of("mystery-model", 1, 1)
        pricer.cost_of("mystery-model", 1, 1)

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "mystery-model" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_a_priced_model_does_not_warn(caplog):
    pricer = UsagePricer(
        _Pricing({"gpt-4o": ModelPrice(input_per_million=10.0, output_per_million=30.0)})
    )

    with caplog.at_level(logging.WARNING):
        pricer.cost_of("gpt-4o", 1_000, 1_000)

    assert caplog.records == []
