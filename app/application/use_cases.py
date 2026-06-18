from app.application.ports import OfferRepository, UserProfileRepository
from app.domain.entities import UserProfile
from app.domain.matching import FilterChain, MatchCriteria, MatchedOffer, OfferScorer


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

    def execute(self, criteria: MatchCriteria, offers_limit: int | None) -> list[MatchedOffer]:
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
        matched_offers.sort(key=lambda m: m.score, reverse=True)
        return matched_offers[:offers_limit]
