from datetime import datetime, timezone

from app.application.ports import BudgetStatusReader, ModelUsageSummary, SpendProvider
from app.domain.budget import BudgetStatus
from app.domain.errors import CostUnavailableError
from app.infrastructure.composite_budget_status_reader import CompositeBudgetStatusReader
from app.infrastructure.model_pricing_registry import HardcodedModelPricingRegistry
from app.infrastructure.org_spend_backstop import OrgSpendBackstop
from app.infrastructure.token_accounting_spend_provider import TokenAccountingSpendProvider
from tests.fakes import FakeModelUsageRepository

_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


# --- HardcodedModelPricingRegistry ---


def test_pricing_matches_a_dated_snapshot_via_prefix():
    registry = HardcodedModelPricingRegistry()

    price = registry.get_price("gpt-4o-2024-08-06")

    assert price is not None
    assert price.input_per_million == 2.50


def test_pricing_prefers_the_longest_matching_prefix():
    registry = HardcodedModelPricingRegistry()

    # gpt-4o-mini must not be priced as gpt-4o.
    assert registry.get_price("gpt-4o-mini").input_per_million == 0.15
    assert registry.get_price("gpt-4o").input_per_million == 2.50


def test_pricing_returns_none_for_unknown_model():
    assert HardcodedModelPricingRegistry().get_price("llama-3-8b") is None


# --- TokenAccountingSpendProvider ---


def test_token_accounting_prices_usage_per_model():
    repo = FakeModelUsageRepository([
        ModelUsageSummary(company="OpenAI", model="gpt-4o", input_tokens=1_000_000, output_tokens=500_000),
    ])
    provider = TokenAccountingSpendProvider(repo, HardcodedModelPricingRegistry())

    # 1M input * $2.50 + 0.5M output * $10.00 = 2.50 + 5.00
    assert provider.spend_since("user-1", _NOW) == 7.50


def test_token_accounting_ignores_models_without_a_known_price():
    repo = FakeModelUsageRepository([
        ModelUsageSummary(company="X", model="mystery-model", input_tokens=1_000_000, output_tokens=1_000_000),
    ])
    provider = TokenAccountingSpendProvider(repo, HardcodedModelPricingRegistry())

    assert provider.spend_since("user-1", _NOW) == 0.0


# --- OrgSpendBackstop ---


class _FixedOrgSpend(SpendProvider):
    def __init__(self, amount: float) -> None:
        self.amount = amount
        self.requested_start: datetime | None = None

    def spend_since(self, start: datetime) -> float:
        self.requested_start = start
        return self.amount


def test_org_backstop_reports_spend_against_global_limit_for_the_utc_day():
    spend = _FixedOrgSpend(12.0)
    backstop = OrgSpendBackstop(spend, limit_usd=20.0, clock=lambda: _NOW)

    status = backstop.status("any-user")

    assert status.used_usd == 12.0
    assert status.limit_usd == 20.0
    assert status.tracking_since == _NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def test_org_backstop_reports_unknown_without_a_provider():
    backstop = OrgSpendBackstop(None, limit_usd=20.0, clock=lambda: _NOW)

    assert backstop.status("any-user").used_usd is None


def test_org_backstop_degrades_to_unknown_when_spend_unavailable():
    class _Failing(SpendProvider):
        def spend_since(self, start: datetime) -> float:
            raise CostUnavailableError("nope")

    backstop = OrgSpendBackstop(_Failing(), limit_usd=20.0, clock=lambda: _NOW)

    assert backstop.status("any-user").used_usd is None


# --- CompositeBudgetStatusReader ---


class _StubReader(BudgetStatusReader):
    def __init__(self, status: BudgetStatus) -> None:
        self._status = status

    def status(self, user_id: str) -> BudgetStatus:
        return self._status


def _status(used: float, limit: float) -> BudgetStatus:
    return BudgetStatus(limit_usd=limit, used_usd=used, tracking_since=_NOW)


def test_composite_returns_first_status_when_none_exceeded():
    composite = CompositeBudgetStatusReader([_StubReader(_status(1.0, 5.0)), _StubReader(_status(2.0, 20.0))])

    assert composite.status("u").exceeded is False
    assert composite.status("u").limit_usd == 5.0


def test_composite_surfaces_the_exceeded_budget():
    user_ok = _StubReader(_status(1.0, 5.0))
    org_over = _StubReader(_status(50.0, 20.0))
    composite = CompositeBudgetStatusReader([user_ok, org_over])

    status = composite.status("u")

    assert status.exceeded is True
    assert status.limit_usd == 20.0  # the breached (org) budget
