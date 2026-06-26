from datetime import datetime, timezone

import pytest

from app.application.ports import ApiKeyRecord, UserProviderSpendProvider
from app.domain.errors import MissingProviderApiKeyError
from app.infrastructure.api_key_budget_status_reader import ApiKeyBudgetStatusReader
from tests.fakes import InMemoryApiKeyRepository

_NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


class _FixedProviderSpend(UserProviderSpendProvider):
    def __init__(self, amount: float):
        self.amount = amount
        self.asked: tuple | None = None

    def spend_since(self, user_id, company, start):
        self.asked = (user_id, company, start)
        return self.amount


def _repo_with_key(limit: float) -> InMemoryApiKeyRepository:
    repo = InMemoryApiKeyRepository()
    repo.add(
        ApiKeyRecord(
            user_id="u1",
            api_provider="openai",
            key_ciphertext="x",
            key_hint="x",
            limit_usd=limit,
            tracking_since=_NOW,
            created_at=_NOW,
        )
    )
    return repo


def test_status_reports_the_keys_limit_and_provider_usage():
    spend = _FixedProviderSpend(3.5)
    reader = ApiKeyBudgetStatusReader(_repo_with_key(10.0), spend, "openai")

    status = reader.status("u1")

    assert status.limit_usd == 10.0
    assert status.used_usd == 3.5
    assert status.tracking_since == _NOW
    assert status.exceeded is False
    # Usage is asked for this provider's company since the key's anchor.
    assert spend.asked == ("u1", "OpenAI", _NOW)


def test_status_is_exceeded_when_provider_spend_reaches_the_limit():
    reader = ApiKeyBudgetStatusReader(_repo_with_key(10.0), _FixedProviderSpend(10.0), "openai")

    assert reader.status("u1").exceeded is True


def test_status_raises_when_the_user_has_no_key_for_the_provider():
    reader = ApiKeyBudgetStatusReader(InMemoryApiKeyRepository(), _FixedProviderSpend(0.0), "openai")

    with pytest.raises(MissingProviderApiKeyError):
        reader.status("u1")
