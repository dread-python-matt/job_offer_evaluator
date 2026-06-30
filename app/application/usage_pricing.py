import logging

from app.application.ports import ModelPricingRegistry

_logger = logging.getLogger(__name__)


class UsagePricer:
    """Prices recorded token usage with the pricing registry.

    A model with no known price contributes **$0** — which would otherwise silently let its
    usage escape every budget — so the first time such a model is seen it is logged at
    WARNING (deduped per instance, so a hot read path doesn't flood the logs). Used both at
    read time (spend providers) and, later, at write time (cost snapshotting)."""

    def __init__(self, pricing: ModelPricingRegistry) -> None:
        self._pricing = pricing
        self._unpriced_seen: set[str] = set()

    def cost_of(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> float:
        price = self._pricing.get_price(model)
        if price is None:
            if model not in self._unpriced_seen:
                self._unpriced_seen.add(model)
                _logger.warning(
                    "No price configured for model %r; its token usage is counted as $0 and "
                    "does not count toward any budget. Add it to the pricing registry.",
                    model,
                )
            return 0.0
        # Cached input is billed at a lower rate (OpenAI); the rest of the input at the normal
        # rate. With no cached rate known, cached tokens cost the normal input rate (so this is
        # never an underestimate). cached_input_tokens is a subset of input_tokens.
        cached = min(cached_input_tokens, input_tokens)
        uncached = input_tokens - cached
        cached_rate = (
            price.cached_input_per_million
            if price.cached_input_per_million is not None
            else price.input_per_million
        )
        return (
            uncached / 1_000_000 * price.input_per_million
            + cached / 1_000_000 * cached_rate
            + output_tokens / 1_000_000 * price.output_per_million
        )
