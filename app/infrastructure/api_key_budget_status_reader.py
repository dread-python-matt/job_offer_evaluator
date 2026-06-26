from app.application.ports import (
    ApiKeyRepository,
    BudgetStatusReader,
    UserProviderSpendProvider,
)
from app.domain.api_providers import company_for_provider
from app.domain.budget import BudgetStatus
from app.domain.errors import MissingProviderApiKeyError


class ApiKeyBudgetStatusReader(BudgetStatusReader):
    """The budget status for one provider key: the key's own limit versus the user's
    derived spend on that provider since the key's anchor. Bound to a fixed `api_provider`
    (the provider of the model being scored), so an AI match is gated by that key's budget.
    Raises MissingProviderApiKeyError if the user has no key for the provider (require own
    key — the match shouldn't have been buildable without one)."""

    def __init__(
        self,
        repository: ApiKeyRepository,
        provider_spend: UserProviderSpendProvider,
        api_provider: str,
    ) -> None:
        self._repository = repository
        self._provider_spend = provider_spend
        self._api_provider = api_provider

    def status(self, user_id: str) -> BudgetStatus:
        record = self._repository.get(user_id, self._api_provider)
        if record is None:
            raise MissingProviderApiKeyError(self._api_provider)
        used = self._provider_spend.spend_since(
            user_id, company_for_provider(self._api_provider), record.tracking_since
        )
        return BudgetStatus(
            limit_usd=record.limit_usd, used_usd=used, tracking_since=record.tracking_since
        )
