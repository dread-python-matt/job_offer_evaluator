from dataclasses import dataclass

from app.application.ports import (
    ExternalUsageProvider,
    ModelLimitsRegistry,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageTracker,
    ModelUsageWithLimits,
    OfferRepository,
    UserProfileRepository,
)
from app.domain.entities import Offer, UserProfile
from app.domain.filters import FilterChain, MatchCriteria, OfferBrowseFilters
from app.domain.salary_calculator import ContractType, NetSalaryBreakdown, SalaryCalculator
from app.domain.scoring import MatchedOffer, OfferScorer
from app.domain.sorting import MatchSortBy, SortOrder, sort_matched_offers


@dataclass
class AiMatchResult:
    matches: list[MatchedOffer]
    usage: list[ModelUsage]


class SaveUserProfileUseCase:
    def __init__(self, profile_repository: UserProfileRepository) -> None:
        self._profile_repository = profile_repository

    def execute(self, profile: UserProfile) -> None:
        self._profile_repository.save(profile)


class GetUserProfileUseCase:
    def __init__(self, profile_repository: UserProfileRepository) -> None:
        self._profile_repository = profile_repository

    def execute(self) -> UserProfile | None:
        return self._profile_repository.load()


class CalculateNetSalaryUseCase:
    def __init__(self, calculator: SalaryCalculator | None = None) -> None:
        self._calculator = calculator or SalaryCalculator()

    def execute(
        self,
        contract_type: ContractType,
        gross_monthly: float,
        business_costs: float = 0.0,
        include_ppk: bool = False,
        include_voluntary_sickness: bool = False,
    ) -> NetSalaryBreakdown:
        return self._calculator.calculate(
            contract_type,
            gross_monthly,
            business_costs=business_costs,
            include_ppk=include_ppk,
            include_voluntary_sickness=include_voluntary_sickness,
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


class MatchOffersUseCase:
    def __init__(
        self,
        offer_repository: OfferRepository,
        offer_scorer: OfferScorer,
        filter_chain: FilterChain,
    ) -> None:
        self._offer_repository = offer_repository
        self._offer_scorer = offer_scorer
        self._filter_chain = filter_chain

    def execute(
        self,
        criteria: MatchCriteria,
        offers_limit: int | None,
        sort_by: MatchSortBy = "score",
        sort_order: SortOrder = "desc",
    ) -> list[MatchedOffer]:
        candidate_offers = [
            offer
            for offer in self._offer_repository.list_offers()
            if self._filter_chain.passes(offer, criteria)
        ]

        matched_offers = [
            MatchedOffer(
                offer=offer,
                score=self._offer_scorer.score(criteria.candidate, offer).overall_score,
                matched_skills=criteria.candidate.skill_names() & offer.skill_set(),
            )
            for offer in candidate_offers
        ]

        matched_offers = [m for m in matched_offers if m.score >= criteria.min_score]
        matched_offers = sort_matched_offers(matched_offers, sort_by, sort_order)
        return matched_offers[:offers_limit]


class MatchOffersWithAiUseCase:
    """Like `MatchOffersUseCase`, but scores offers with an (expensive) AI scorer
    instead of a cheap deterministic one. To bound cost/latency, filtered candidates
    are pre-ranked with `ranking_scorer` and only the top `offers_to_score` are sent
    to `ai_scorer`."""

    def __init__(
        self,
        offer_repository: OfferRepository,
        filter_chain: FilterChain,
        ranking_scorer: OfferScorer,
        ai_scorer: OfferScorer,
        usage_tracker: ModelUsageTracker | None = None,
    ) -> None:
        self._offer_repository = offer_repository
        self._filter_chain = filter_chain
        self._ranking_scorer = ranking_scorer
        self._ai_scorer = ai_scorer
        self._usage_tracker = usage_tracker

    def execute(
        self,
        criteria: MatchCriteria,
        offers_to_score: int,
        offers_limit: int | None,
        sort_by: MatchSortBy = "score",
        sort_order: SortOrder = "desc",
        ai_min_score: float = 0.0,
    ) -> AiMatchResult:
        candidate_offers = [
            offer
            for offer in self._offer_repository.list_offers()
            if self._filter_chain.passes(offer, criteria)
        ]

        ranked_offers = sorted(
            candidate_offers,
            key=lambda offer: self._ranking_scorer.score(criteria.candidate, offer).overall_score,
            reverse=True,
        )
        offers_to_send = ranked_offers[:offers_to_score]

        matched_offers = [
            MatchedOffer(
                offer=offer,
                score=self._ai_scorer.score(criteria.candidate, offer).overall_score,
                matched_skills=criteria.candidate.skill_names() & offer.skill_set(),
            )
            for offer in offers_to_send
        ]

        matched_offers = [m for m in matched_offers if m.score >= ai_min_score]
        matched_offers = sort_matched_offers(matched_offers, sort_by, sort_order)
        usage = self._usage_tracker.flush() if self._usage_tracker else []
        return AiMatchResult(matches=matched_offers[:offers_limit], usage=usage)


class GetModelUsageSummaryUseCase:
    def __init__(
        self,
        repository: ModelUsageRepository,
        limits_registry: ModelLimitsRegistry,
        external_provider: ExternalUsageProvider | None = None,
    ) -> None:
        self._repository = repository
        self._limits_registry = limits_registry
        self._external_provider = external_provider

    def execute(self) -> list[ModelUsageWithLimits]:
        if self._external_provider:
            summaries = self._external_provider.get_today_usage()
            if summaries:
                return self._enrich(summaries)
        return self._enrich(self._repository.get_summary())

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
