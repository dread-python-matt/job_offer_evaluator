from app.application.ports import BudgetStatusReader
from app.domain.budget import BudgetStatus


class CompositeBudgetStatusReader(BudgetStatusReader):
    """Combines several budgets (e.g. a user's token budget plus a global org backstop).
    If any is exceeded, that one's status is returned so the resulting error reflects the
    breached budget; otherwise the first reader's status is returned."""

    def __init__(self, readers: list[BudgetStatusReader]) -> None:
        if not readers:
            raise ValueError("CompositeBudgetStatusReader requires at least one reader")
        self._readers = readers

    def status(self, user_id: str) -> BudgetStatus:
        statuses = [reader.status(user_id) for reader in self._readers]
        for status in statuses:
            if status.exceeded:
                return status
        return statuses[0]
