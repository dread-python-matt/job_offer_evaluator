from app.application.ports import ModelPrice, ModelPricingRegistry

# USD per 1,000,000 tokens (input, output[, cached input]), keyed by model-id prefix so dated
# snapshots (e.g. gpt-4o-2024-08-06) inherit their family's price. Longest prefix wins.
# Approximate public list prices — good enough for a budget guard, not invoicing.
# The third value is the discounted prompt-cache (cached input) rate; OpenAI bills cache hits
# below the normal input rate. Gemini entries omit it (priced at the normal input rate).
_PRICES: list[tuple[str, ModelPrice]] = [
    ("gpt-4o-mini", ModelPrice(0.15, 0.60, 0.075)),
    ("gpt-4o", ModelPrice(2.50, 10.00, 1.25)),
    ("gpt-4.1-nano", ModelPrice(0.10, 0.40, 0.025)),
    ("gpt-4.1-mini", ModelPrice(0.40, 1.60, 0.10)),
    ("gpt-4.1", ModelPrice(2.00, 8.00, 0.50)),
    ("gpt-5", ModelPrice(1.25, 10.00, 0.125)),
    ("o1-mini", ModelPrice(1.10, 4.40, 0.55)),
    ("o1", ModelPrice(15.00, 60.00, 7.50)),
    ("o3-mini", ModelPrice(1.10, 4.40, 0.55)),
    ("o3", ModelPrice(2.00, 8.00, 0.50)),
    ("o4-mini", ModelPrice(1.10, 4.40, 0.275)),
    # Flash-Lite / Flash-8B are cheaper than their Flash parents; explicit entries keep the
    # longest-prefix match from inheriting (and overcharging at) the parent's price.
    ("gemini-2.0-flash-lite", ModelPrice(0.075, 0.30)),
    ("gemini-2.0-flash", ModelPrice(0.10, 0.40)),
    ("gemini-1.5-flash-8b", ModelPrice(0.0375, 0.15)),
    ("gemini-1.5-flash", ModelPrice(0.075, 0.30)),
    ("gemini-1.5-pro", ModelPrice(1.25, 5.00)),
    ("gemini-2.5-pro", ModelPrice(1.25, 10.00)),
    ("gemini-2.5-flash", ModelPrice(0.30, 2.50)),
]


class HardcodedModelPricingRegistry(ModelPricingRegistry):
    def get_price(self, model: str) -> ModelPrice | None:
        best: tuple[str, ModelPrice] | None = None
        for prefix, price in _PRICES:
            if model.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, price)
        return best[1] if best is not None else None
