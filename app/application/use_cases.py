import asyncio
import logging
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.application.ports import (
    AvailableModel,
    BudgetStatusReader,
    DailyRequestUsageReader,
    ExternalUsageProvider,
    ModelLimitsRegistry,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageSummary,
    ModelUsageTracker,
    ModelUsageWithLimits,
    OfferRepository,
    SpendProvider,
    UserAvailableModelsProvider,
    UserProfileRepository,
)
from app.application.skill_canonicalization import SkillCanonicalizer
from app.domain.errors import (
    AiScoringError,
    BudgetExceededError,
    CostUnavailableError,
    DailyRequestLimitExceededError,
)
from app.domain.entities import Offer, TaxSituation, UserProfile
from app.domain.filters import FilterChain, MatchCriteria, OfferBrowseFilters
from app.domain.salary_calculator import (
    ContractType,
    NetSalaryBreakdown,
    SalaryCalculator,
)
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
    def __init__(
        self,
        offer_repository: OfferRepository,
        filter_chain: FilterChain,
        canonicalizer: SkillCanonicalizer | None = None,
    ) -> None:
        self._offer_repository = offer_repository
        self._filter_chain = filter_chain
        # Skill tokens are collapsed to canonical concepts before any comparison, so e.g. "JS"
        # matches "JavaScript". Defaults to a no-op canonicalizer, so callers/tests that don't
        # wire a normalizer keep exact literal behavior; production injects a real one (main.py).
        self._canonicalizer = canonicalizer or SkillCanonicalizer()

    def _passing_candidates(
        self, criteria: MatchCriteria, canon_criteria: MatchCriteria
    ) -> list[tuple[Offer, Offer]]:
        # The repository pushes the structural filters into the data store using the ORIGINAL
        # criteria (so the whole offers table is never materialized); the FilterChain then
        # applies exact domain semantics — incl. the candidate SkillFilter — on the CANONICAL
        # offer/candidate, so skill overlap is judged by concept. Each surviving offer is kept
        # as (original, canonical): the original is shown to the user, the canonical is scored.
        pairs: list[tuple[Offer, Offer]] = []
        for offer in self._offer_repository.candidate_offers(criteria):
            canon_offer = self._canonicalizer.canonicalize_offer(offer)
            if self._filter_chain.passes(canon_offer, canon_criteria):
                pairs.append((offer, canon_offer))
        return pairs

    def _make_matched(
        self,
        offer: Offer,
        score: float,
        canon_candidate: UserProfile,
        canon_offer: Offer,
        ai_insight: AiInsight | None = None,
    ) -> MatchedOffer:
        return MatchedOffer(
            offer=offer,
            score=score,
            # Concept overlap, so it reflects true matches regardless of how either side spelled
            # them (e.g. "JS" vs "JavaScript").
            matched_skills=canon_candidate.skill_names() & canon_offer.skill_set(),
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
        canonicalizer: SkillCanonicalizer | None = None,
    ) -> None:
        super().__init__(offer_repository, filter_chain, canonicalizer)
        self._offer_scorer = offer_scorer

    def execute(
        self,
        criteria: MatchCriteria,
        offers_limit: int | None,
        sort_by: MatchSortBy = "score",
        sort_order: SortOrder = "desc",
    ) -> list[MatchedOffer]:
        canon_candidate = self._canonicalizer.canonicalize_candidate(criteria.candidate)
        canon_criteria = replace(criteria, candidate=canon_candidate)
        matched = [
            self._make_matched(
                offer,
                self._offer_scorer.score(canon_candidate, canon_offer).overall_score,
                canon_candidate,
                canon_offer,
            )
            for offer, canon_offer in self._passing_candidates(criteria, canon_criteria)
        ]
        return self._finalize(
            matched, criteria.min_score, sort_by, sort_order, offers_limit
        )


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
        canonicalizer: SkillCanonicalizer | None = None,
        daily_request_reader: DailyRequestUsageReader | None = None,
        scoring_model: str = "",
    ) -> None:
        super().__init__(offer_repository, filter_chain, canonicalizer)
        self._ranking_scorer = ranking_scorer
        self._ai_scorer = ai_scorer
        self._usage_tracker = usage_tracker
        self._usage_repository = usage_repository
        self._budget = budget
        self._max_concurrency = max_concurrency
        self._fail_closed = fail_closed
        # Optional per-day request gate (free-tier-friendly), enforced for `scoring_model`
        # alongside the USD budget. No-op when unset or when the reader reports no daily cap.
        self._daily_request_reader = daily_request_reader
        self._scoring_model = scoring_model

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
        """Synchronous entry point (tests and sync callers). Runs the AI scoring in a
        private event loop; prefer `execute_async` from an async route so the slow
        round-trips don't pin a worker thread."""
        canon_candidate = self._canonicalizer.canonicalize_candidate(criteria.candidate)
        ranked = self._prepare(criteria, canon_candidate, offers_to_score, user_id)
        scored = asyncio.run(self._score_concurrently(canon_candidate, ranked))
        return self._build_result(
            scored,
            canon_candidate,
            ai_min_score,
            sort_by,
            sort_order,
            offers_limit,
            user_id,
        )

    async def execute_async(
        self,
        criteria: MatchCriteria,
        offers_to_score: int,
        offers_limit: int | None,
        sort_by: MatchSortBy = "score",
        sort_order: SortOrder = "desc",
        ai_min_score: float = 0.0,
        user_id: str = "",
    ) -> AiMatchResult:
        """Async entry point: awaits the AI scoring on the caller's event loop instead of
        spinning up a private loop inside a worker thread, so many matches can be in flight
        at once without exhausting the server's thread pool while each waits on its LLM
        round-trips."""
        canon_candidate = self._canonicalizer.canonicalize_candidate(criteria.candidate)
        ranked = self._prepare(criteria, canon_candidate, offers_to_score, user_id)
        scored = await self._score_concurrently(canon_candidate, ranked)
        return self._build_result(
            scored,
            canon_candidate,
            ai_min_score,
            sort_by,
            sort_order,
            offers_limit,
            user_id,
        )

    def _prepare(
        self,
        criteria: MatchCriteria,
        canon_candidate: UserProfile,
        offers_to_score: int,
        user_id: str,
    ) -> list[tuple[Offer, Offer]]:
        """Shared pre-scoring steps for both entry points: the budget gate, opening a fresh
        usage scope, and loading + ranking candidates down to the top `offers_to_score`.
        Returns (original, canonical) offer pairs."""
        if self._budget:
            status = self._budget.status(user_id)
            if status.exceeded:
                raise BudgetExceededError(status.used_usd, status.limit_usd)
            if self._fail_closed and status.used_usd is None:
                raise AiScoringError(
                    "AI spend is currently unavailable and the budget is fail-closed; "
                    "refusing to score."
                )
        # Per-day request gate (e.g. Gemini free-tier RPD), independent of the USD budget.
        if self._daily_request_reader is not None and self._scoring_model:
            daily = self._daily_request_reader.status_for(user_id, self._scoring_model)
            if daily is not None and daily.exceeded:
                raise DailyRequestLimitExceededError(
                    daily.used, daily.limit, self._scoring_model
                )
        # Open a fresh usage scope for this request, in this context, before any concurrent
        # scoring tasks are spawned — so usage is attributed to this user only (no cross-
        # tenant bleed) and nothing from a prior aborted request leaks in.
        if self._usage_tracker is not None:
            self._usage_tracker.begin()
        canon_criteria = replace(criteria, candidate=canon_candidate)
        ranked = sorted(
            self._passing_candidates(criteria, canon_criteria),
            key=lambda pair: (
                self._ranking_scorer.score(canon_candidate, pair[1]).overall_score
            ),
            reverse=True,
        )
        return ranked[:offers_to_score]

    def _build_result(
        self,
        scored: list[tuple[Offer, Offer, MatchScore]],
        canon_candidate: UserProfile,
        ai_min_score: float,
        sort_by: MatchSortBy,
        sort_order: SortOrder,
        offers_limit: int | None,
        user_id: str,
    ) -> AiMatchResult:
        """Shared post-scoring steps: build matched offers, persist this request's usage,
        and finalize (min-score filter, sort, limit)."""
        matched = [
            self._make_matched(
                offer,
                score.overall_score,
                canon_candidate,
                canon_offer,
                ai_insight=score.metadata("ai_insight"),
            )
            for offer, canon_offer, score in scored
        ]
        usage = self._persist_usage(user_id)
        return AiMatchResult(
            matches=self._finalize(
                matched, ai_min_score, sort_by, sort_order, offers_limit
            ),
            usage=usage,
        )

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
        self, canon_candidate: UserProfile, pairs: list[tuple[Offer, Offer]]
    ) -> list[tuple[Offer, Offer, MatchScore]]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def score_one(
            pair: tuple[Offer, Offer],
        ) -> tuple[Offer, Offer, MatchScore]:
            original, canon_offer = pair
            async with semaphore:
                score = await self._ai_scorer.score_async(canon_candidate, canon_offer)
                return original, canon_offer, score

        results = await asyncio.gather(
            *(score_one(pair) for pair in pairs), return_exceptions=True
        )
        scored = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        for exc in failures:
            _logger.warning("Skipping offer; AI scoring failed: %s", exc)
        if pairs and not scored:
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


@dataclass(frozen=True)
class OrgUsage:
    """The organization's actual per-model token usage (from the admin usage API) since
    `since`. Org-wide, not attributable per user."""

    models: list[ModelUsageSummary]
    since: datetime


class GetOrgUsageUseCase:
    """Reads the organization's real per-model token usage for the current UTC day from the
    admin usage API (OpenAI's completions-usage endpoint, via the admin key). These are the
    provider's authoritative counts, unlike the app's own per-request accounting. Returns
    None when no usage provider is configured (no admin key, or a non-OpenAI provider) or the
    figure is currently unavailable, so the UI can degrade gracefully rather than error.

    The result is org-wide and cannot be attributed per user — it is an owner/admin readout,
    distinct from the per-user `/usage/summary`."""

    def __init__(
        self,
        usage_provider: ExternalUsageProvider | None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._usage_provider = usage_provider
        self._clock = clock

    def execute(self) -> OrgUsage | None:
        if self._usage_provider is None:
            return None
        since = _start_of_utc_day(self._clock())
        try:
            models = self._usage_provider.get_today_usage()
        except CostUnavailableError:
            return None
        return OrgUsage(models=models, since=since)


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
