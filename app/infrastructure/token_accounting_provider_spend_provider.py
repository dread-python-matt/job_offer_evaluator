from datetime import datetime

from app.application.ports import ModelUsageRepository, UserProviderSpendProvider


class TokenAccountingProviderSpendProvider(UserProviderSpendProvider):
    """Per-user, per-provider spend derived from this app's own token accounting: sums the
    write-time USD cost snapshotted onto the user's recorded usage rows for a single company's
    models since `start`. Usage on models that had no known price when recorded contributes $0,
    so the figure is a lower-bound estimate — acceptable for a best-effort per-key budget."""

    def __init__(self, usage_repository: ModelUsageRepository) -> None:
        self._usage_repository = usage_repository

    def spend_since(self, user_id: str, company: str, start: datetime) -> float:
        return sum(
            s.cost_usd
            for s in self._usage_repository.usage_since(user_id, start)
            if s.company == company
        )
