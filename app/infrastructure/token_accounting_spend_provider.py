from datetime import datetime

from app.application.ports import ModelUsageRepository, UserSpendProvider


class TokenAccountingSpendProvider(UserSpendProvider):
    """Per-user spend derived from this app's own token accounting: sums the USD cost that
    was snapshotted onto each of the user's recorded usage rows (priced once at write time)
    since `start`. Usage on models that had no known price when recorded contributes $0, so
    the figure is a lower bound — acceptable for a best-effort budget guard."""

    def __init__(self, usage_repository: ModelUsageRepository) -> None:
        self._usage_repository = usage_repository

    def spend_since(self, user_id: str, start: datetime) -> float:
        return sum(s.cost_usd for s in self._usage_repository.usage_since(user_id, start))
