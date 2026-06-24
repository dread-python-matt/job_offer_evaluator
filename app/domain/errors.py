class AiScoringError(Exception):
    pass


class CostUnavailableError(Exception):
    """Raised when the daily cost cannot be determined (e.g. the usage API is
    unauthorized, lacks scopes, or is unreachable). Callers treat this as
    'budget unknown' and degrade gracefully rather than failing the request."""


class BudgetExceededError(Exception):
    def __init__(self, cost_usd: float, limit_usd: float) -> None:
        super().__init__(
            f"Daily OpenAI budget exceeded: ${cost_usd:.2f} spent of ${limit_usd:.2f} limit"
        )
        self.cost_usd = cost_usd
        self.limit_usd = limit_usd
