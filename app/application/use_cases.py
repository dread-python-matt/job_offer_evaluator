from app.application.ports import OfferRepository, UserProfileRepository
from app.domain.entities import UserProfile
from app.domain.matching import MatchedOffer, ScoringStrategy


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
        scoring_strategy: ScoringStrategy,
    ) -> None:
        self._offer_repository = offer_repository
        self._scoring_strategy = scoring_strategy

    def execute(self, candidate: UserProfile, offers_limit: int, min_score: float) -> list[MatchedOffer]:
        matched_offers = [
            MatchedOffer(
                offer=offer,
                score=self._scoring_strategy.score(candidate, offer).overall_score,
                matched_skills=candidate.skill_names() & offer.skill_set(),
            )
            for offer in self._offer_repository.list_offers()
        ]

        matched_offers = [m for m in matched_offers if m.score >= min_score]
        matched_offers.sort(key=lambda m: m.score, reverse=True)
        return matched_offers[:offers_limit]
