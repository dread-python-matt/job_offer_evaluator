from datetime import datetime

from app.application.ports import (
    BudgetRepository,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageSummary,
    OfferRepository,
    SpendProvider,
    UserProfileRepository,
)
from app.domain.budget import BudgetSettings
from app.domain.entities import Offer, UserProfile
from app.domain.filters import (
    OfferBrowseFilters,
    expired_matches,
    level_matches,
    location_matches,
    salary_meets_minimum,
    tech_stack_matches,
    text_matches,
)
from app.domain.scoring import MatchScore, OfferScorer, ScoreComponent
from app.domain.sorting import sort_offers


class InMemoryBudgetRepository(BudgetRepository):
    def __init__(self, settings: BudgetSettings) -> None:
        self.settings = settings

    def load(self) -> BudgetSettings:
        return self.settings

    def save(self, settings: BudgetSettings) -> None:
        self.settings = settings


class FixedSpendProvider(SpendProvider):
    """Returns a fixed spend and records the start instant it was asked about."""

    def __init__(self, amount: float) -> None:
        self.amount = amount
        self.requested_start: datetime | None = None

    def spend_since(self, start: datetime) -> float:
        self.requested_start = start
        return self.amount


class FakeUserProfileRepository(UserProfileRepository):
    def __init__(self, profile: UserProfile | None = None) -> None:
        self.profile = profile

    def save(self, profile: UserProfile) -> None:
        self.profile = profile

    def load(self) -> UserProfile | None:
        return self.profile


class FakeOfferRepository(OfferRepository):
    def __init__(self, offers: list[Offer]) -> None:
        self.offers = offers

    def list_offers(self) -> list[Offer]:
        return self.offers

    def count_offers(self) -> int:
        return len(self.offers)

    def browse_offers(
        self, filters: OfferBrowseFilters, limit: int, offset: int
    ) -> tuple[list[Offer], int]:
        matching = [o for o in self.offers if self._matches(o, filters)]
        matching = sort_offers(matching, filters.sort_by, filters.sort_order)
        return matching[offset : offset + limit], len(matching)

    def _matches(self, offer: Offer, filters: OfferBrowseFilters) -> bool:
        return (
            expired_matches(offer, filters.include_expired)
            and location_matches(offer, filters.location)
            and salary_meets_minimum(offer, filters.min_salary)
            and tech_stack_matches(offer, filters.tech)
            and text_matches(offer, filters.search)
            and level_matches(offer, filters.level)
        )


class FakeModelUsageRepository(ModelUsageRepository):
    def __init__(self, summaries: list[ModelUsageSummary] | None = None) -> None:
        self._summaries = summaries or []
        self.saved: list[ModelUsage] = []

    def save(self, usage: ModelUsage) -> None:
        self.saved.append(usage)

    def get_summary(self) -> list[ModelUsageSummary]:
        return self._summaries


class ScoreByLinkScorer(OfferScorer):
    """Scores offers by a fixed link→score mapping; records which offers were scored."""

    def __init__(self, scores_by_link: dict[str, float]) -> None:
        self._scores_by_link = scores_by_link
        self.scored_links: list[str] = []

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        self.scored_links.append(offer.link)
        return MatchScore().with_component(
            ScoreComponent(name="fixed", value=self._scores_by_link[offer.link], weight=1.0)
        )
