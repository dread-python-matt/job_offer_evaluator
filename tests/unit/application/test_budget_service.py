from datetime import datetime, timedelta, timezone

from app.application.budget_service import BudgetService
from app.application.ports import UserSpendProvider
from app.domain.budget import BudgetSettings
from app.domain.errors import CostUnavailableError
from tests.fakes import FixedUserSpendProvider, InMemoryBudgetRepository

ANCHOR = datetime(2026, 6, 1, tzinfo=timezone.utc)
USER = "user-1"


class FailingSpendProvider(UserSpendProvider):
    def spend_since(self, user_id: str, start: datetime) -> float:
        raise CostUnavailableError("Missing scopes: api.usage.read")


def _repo(limit: float = 5.0, since: datetime = ANCHOR) -> InMemoryBudgetRepository:
    return InMemoryBudgetRepository(BudgetSettings(limit_usd=limit, tracking_since=since))


def test_status_combines_stored_limit_with_spend_since_anchor():
    spend = FixedUserSpendProvider(3.5)
    service = BudgetService(_repo(limit=10.0), spend)

    status = service.status(USER)

    assert status.limit_usd == 10.0
    assert status.used_usd == 3.5
    assert status.tracking_since == ANCHOR
    assert spend.requested_start == ANCHOR
    assert spend.requested_user == USER


def test_status_reports_unknown_usage_when_spend_unavailable():
    service = BudgetService(_repo(), FailingSpendProvider())

    assert service.status(USER).used_usd is None


def test_status_reports_unknown_usage_when_no_spend_provider():
    service = BudgetService(_repo(), None)

    assert service.status(USER).used_usd is None


def test_budgets_are_isolated_per_user():
    repo = _repo(limit=5.0)
    service = BudgetService(repo, FixedUserSpendProvider(1.0))

    service.set_limit("alice", 20.0)

    assert service.status("alice").limit_usd == 20.0
    assert service.status("bob").limit_usd == 5.0  # bob still on the default


def test_set_limit_persists_new_limit_and_keeps_anchor():
    repo = _repo(limit=5.0)
    service = BudgetService(repo, FixedUserSpendProvider(1.0))

    status = service.set_limit(USER, 20.0)

    assert status.limit_usd == 20.0
    assert repo.load(USER).limit_usd == 20.0
    assert repo.load(USER).tracking_since == ANCHOR


def test_reset_usage_moves_anchor_to_now():
    now = datetime(2026, 6, 24, tzinfo=timezone.utc)
    repo = _repo(since=ANCHOR)
    service = BudgetService(repo, FixedUserSpendProvider(0.0), clock=lambda: now)

    status = service.reset_usage(USER)

    assert status.tracking_since == now
    assert repo.load(USER).tracking_since == now


def test_status_is_exceeded_when_usage_reaches_limit():
    service = BudgetService(_repo(limit=5.0), FixedUserSpendProvider(5.0))

    assert service.status(USER).exceeded is True


class _ManualClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def test_spend_is_cached_within_ttl():
    spend = FixedUserSpendProvider(2.0)
    clock = _ManualClock(datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc))
    service = BudgetService(_repo(), spend, clock=clock, cache_ttl_seconds=60)

    service.status(USER)
    service.status(USER)  # within TTL -> served from cache

    assert spend.calls == 1


def test_spend_cache_is_per_user():
    spend = FixedUserSpendProvider(2.0)
    clock = _ManualClock(datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc))
    service = BudgetService(_repo(), spend, clock=clock, cache_ttl_seconds=60)

    service.status("alice")
    service.status("bob")  # different user -> not served from alice's cache

    assert spend.calls == 2


def test_spend_is_refetched_after_ttl_expires():
    spend = FixedUserSpendProvider(2.0)
    clock = _ManualClock(datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc))
    service = BudgetService(_repo(), spend, clock=clock, cache_ttl_seconds=60)

    service.status(USER)
    clock.now += timedelta(seconds=61)
    service.status(USER)

    assert spend.calls == 2


def test_reset_invalidates_spend_cache_via_new_anchor():
    spend = FixedUserSpendProvider(2.0)
    clock = _ManualClock(datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc))
    service = BudgetService(_repo(), spend, clock=clock, cache_ttl_seconds=60)

    service.status(USER)
    service.reset_usage(USER)  # moves the anchor -> cache key changes

    assert spend.calls == 2
    assert spend.requested_start == clock.now
