import asyncio
import logging
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.application.ports import (
    AvailableModel,
    BudgetStatusReader,
    ModelLimitsRegistry,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageTracker,
    ModelUsageWithLimits,
    OfferRepository,
    SpendProvider,
    UserAvailableModelsProvider,
    UserProfileRepository,
)
from app.domain.errors import AiScoringError, BudgetExceededError, CostUnavailableError
from app.domain.entities import Offer, TaxSituation, UserProfile
from app.domain.filters import FilterChain, MatchCriteria, OfferBrowseFilters
from app.domain.salary_calculator import ContractType, NetSalaryBreakdown, SalaryCalculator
from app.domain.scoring import AiInsight, MatchedOffer, MatchScore, OfferScorer
from app.domain.sorting import MatchSortBy, SortOrder, sort_matched_offers

_logger = logging.getLogger(__name__)


@dataclass
class AiMatchResult:
    matches: list[MatchedOffer]
    usage: list[ModelUsage]


class SaveUserProfileUseCase:
    def __init__(self, profile_repository: UserProfileRepository) -> None:
        self._profile_repository = profile_repository

    def execute(self, user_id: str, profile: UserProfile) -> None:
        self._profile_repository.save(user_id, profile)


class GetUserProfileUseCase:
    def __init__(self, profile_repository: UserProfileRepository) -> None:
        self._profile_repository = profile_repository

    def execute(self, user_id: str) -> UserProfile | None:
        return self._profile_repository.load(user_id)


class CalculateNetSalaryUseCase:
    def __init__(self, calculator: SalaryCalculator) -> None:
        self._calculator = calculator

    def execute(
        self,
        contract_type: ContractType,
        gross_monthly: float,
        business_costs: float = 0.0,
        include_ppk: bool = False,
        include_voluntary_sickness: bool = False,
        situation: TaxSituation | None = None,
    ) -> NetSalaryBreakdown:
        return self._calculator.calculate(
            contract_type,
            gross_monthly,
            business_costs=business_costs,
            include_ppk=include_ppk,
            include_voluntary_sickness=include_voluntary_sickness,
            situation=situation,
        )


class CountOffersUseCase:
    def __init__(self, offer_repository: OfferRepository) -> None:
        self._offer_repository = offer_repository

    def execute(self) -> int:
        return self._offer_repository.count_offers()


class ListOffersUseCase:
    def __init__(self, offer_repository: OfferRepository) -> None:
        self._offer_repository = offer_repository

    def execute(
        self, limit: int, offset: int, filters: OfferBrowseFilters
    ) -> tuple[list[Offer], int]:
        return self._offer_repository.browse_offers(filters, limit, offset)


class _BaseMatchOffersUseCase(ABC):
    def __init__(self, offer_repository: OfferRepository, filter_chain: FilterChain) -> None:
        self._offer_repository = offer_repository
        self._filter_chain = filter_chain

    def _load_candidates(self, criteria: MatchCriteria) -> list[Offer]:
        return [
            offer
            for offer in self._offer_repository.list_offers()
            if self._filter_chain.passes(offer, criteria)
        ]

    def _make_matched(
        self,
        offer: Offer,
        score: float,
        criteria: MatchCriteria,
        ai_insight: AiInsight | None = None,
    ) -> MatchedOffer:
        return MatchedOffer(
            offer=offer,
            score=score,
            matched_skills=criteria.candidate.skill_names() & offer.skill_set(),
            ai_insight=ai_insight,
        )

    def _finalize(
        self,
        matched: list[MatchedOffer],
        min_score: float,
        sort_by: MatchSortBy,
        sort_order: SortOrder,
        offers_limit: int | None,
    ) -> list[MatchedOffer]:
        filtered = [m for m in matched if m.score >= min_score]
        return sort_matched_offers(filtered, sort_by, sort_order)[:offers_limit]


class MatchOffersUseCase(_BaseMatchOffersUseCase):
    def __init__(
        self,
        offer_repository: OfferRepository,
        offer_scorer: OfferScorer,
        filter_chain: FilterChain,
    ) -> None:
        super().__init__(offer_repository, filter_chain)
        self._offer_scorer = offer_scorer

    def execute(
        self,
        criteria: MatchCriteria,
        offers_limit: int | None,
        sort_by: MatchSortBy = "score",
        sort_order: SortOrder = "desc",
    ) -> list[MatchedOffer]:
        candidates = self._load_candidates(criteria)
        matched = [
            self._make_matched(offer, self._offer_scorer.score(criteria.candidate, offer).overall_score, criteria)
            for offer in candidates
        ]
        return self._finalize(matched, criteria.min_score, sort_by, sort_order, offers_limit)


class MatchOffersWithAiUseCase(_BaseMatchOffersUseCase):
    """Like `MatchOffersUseCase`, but scores offers with an (expensive) AI scorer
    instead of a cheap deterministic one. To bound cost/latency, filtered candidates
    are pre-ranked with `ranking_scorer` and only the top `offers_to_score` are sent
    to `ai_scorer`.

    When `budget` is set, raises `BudgetExceededError` before scoring if usage has
    reached or exceeded the configured limit. If the spend figure is unavailable the
    behaviour depends on `fail_closed`: by default the match proceeds (fail-open
    guardrail); when `fail_closed` is True it raises `AiScoringError` rather than
    risk unbounded spend it can't measure.

    The top `offers_to_score` offers are scored concurrently (up to `max_concurrency`
    at once) since each AI call is a slow, I/O-bound round-trip. Scoring is best-effort:
    an offer whose scoring fails is dropped from the results, but if every offer fails
    the error is raised so callers see the outage rather than a silently empty match."""

    def __init__(
        self,
        offer_repository: OfferRepository,
        filter_chain: FilterChain,
        ranking_scorer: OfferScorer,
        ai_scorer: OfferScorer,
        usage_tracker: ModelUsageTracker | None = None,
        usage_repository: ModelUsageRepository | None = None,
        budget: BudgetStatusReader | None = None,
        max_concurrency: int = 10,
        fail_closed: bool = False,
    ) -> None:
        super().__init__(offer_repository, filter_chain)
        self._ranking_scorer = ranking_scorer
        self._ai_scorer = ai_scorer
        self._usage_tracker = usage_tracker
        self._usage_repository = usage_repository
        self._budget = budget
        self._max_concurrency = max_concurrency
        self._fail_closed = fail_closed

    def execute(
        self,
        criteria: MatchCriteria,
        offers_to_score: int,
        offers_limit: int | None,
        sort_by: MatchSortBy = "score",
        sort_order: SortOrder = "desc",
        ai_min_score: float = 0.0,
        user_id: str = "",
    ) -> AiMatchResult:
        if self._budget:
            status = self._budget.status(user_id)
            if status.exceeded:
                raise BudgetExceededError(status.used_usd, status.limit_usd)
            if self._fail_closed and status.used_usd is None:
                raise AiScoringError(
                    "AI spend is currently unavailable and the budget is fail-closed; "
                    "refusing to score."
                )
        # Open a fresh usage scope for this request, in this context, before any concurrent
        # scoring tasks are spawned — so usage is attributed to this user only (no cross-
        # tenant bleed) and nothing from a prior aborted request leaks in.
        if self._usage_tracker is not None:
            self._usage_tracker.begin()
        candidates = self._load_candidates(criteria)
        ranked = sorted(
            candidates,
            key=lambda offer: self._ranking_scorer.score(criteria.candidate, offer).overall_score,
            reverse=True,
        )
        scored = asyncio.run(self._score_concurrently(criteria.candidate, ranked[:offers_to_score]))
        matched = [
            self._make_matched(
                offer, score.overall_score, criteria, ai_insight=score.metadata("ai_insight")
            )
            for offer, score in scored
        ]
        usage = self._persist_usage(user_id)
        return AiMatchResult(matches=self._finalize(matched, ai_min_score, sort_by, sort_order, offers_limit), usage=usage)

    def _persist_usage(self, user_id: str) -> list[ModelUsage]:
        """Drain this request's recorded token usage, stamp it with the calling user,
        and persist it (so per-user usage and budgets are attributed correctly)."""
        usage = [
            replace(u, user_id=user_id)
            for u in (self._usage_tracker.flush() if self._usage_tracker else [])
        ]
        if self._usage_repository is not None:
            for record in usage:
                self._usage_repository.save(record)
        return usage

    async def _score_concurrently(
        self, candidate: UserProfile, offers: list[Offer]
    ) -> list[tuple[Offer, MatchScore]]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def score_one(offer: Offer) -> tuple[Offer, MatchScore]:
            async with semaphore:
                return offer, await self._ai_scorer.score_async(candidate, offer)

        results = await asyncio.gather(
            *(score_one(offer) for offer in offers), return_exceptions=True
        )
        scored = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        for exc in failures:
            _logger.warning("Skipping offer; AI scoring failed: %s", exc)
        if offers and not scored:
            raise failures[0]
        return scored


@dataclass(frozen=True)
class OrgSpend:
    """The organization's actual provider spend (real money, from the admin usage API)
    since `since`. Org-wide, not attributable per user."""

    spend_usd: float
    since: datetime


def _start_of_utc_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class GetOrgSpendUseCase:
    """Reads the organization's real provider spend for the current UTC day from the admin
    usage API (e.g. OpenAI's costs endpoint, via the admin key). Returns None when no spend
    provider is configured (no admin key) or the figure is currently unavailable, so the UI
    can degrade gracefully rather than error."""

    def __init__(
        self,
        spend_provider: SpendProvider | None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._spend_provider = spend_provider
        self._clock = clock

    def execute(self) -> OrgSpend | None:
        if self._spend_provider is None:
            return None
        since = _start_of_utc_day(self._clock())
        try:
            spend = self._spend_provider.spend_since(since)
        except CostUnavailableError:
            return None
        return OrgSpend(spend_usd=spend, since=since)


class ListAvailableModelsUseCase:
    """The models the calling user can run, discovered from their own provider keys
    (require own key). A user with no keys gets an empty list."""

    def __init__(self, provider: UserAvailableModelsProvider) -> None:
        self._provider = provider

    def execute(self, user_id: str) -> list[AvailableModel]:
        return self._provider.list_models(user_id)


class GetModelUsageSummaryUseCase:
    """Per-user token usage, summed from this app's own accounting (the model_usage
    table). The provider's org-level usage API can't be attributed per user, so it is
    not used here."""

    def __init__(
        self,
        repository: ModelUsageRepository,
        limits_registry: ModelLimitsRegistry,
    ) -> None:
        self._repository = repository
        self._limits_registry = limits_registry

    def execute(self, user_id: str) -> list[ModelUsageWithLimits]:
        return self._enrich(self._repository.get_summary(user_id))

    def _enrich(self, summaries: list) -> list[ModelUsageWithLimits]:
        return [
            ModelUsageWithLimits(
                company=s.company,
                model=s.model,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                limits=self._limits_registry.get_limits(s.model),
            )
            for s in summaries
        ]
