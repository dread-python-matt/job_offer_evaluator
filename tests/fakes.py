from datetime import datetime

from app.application.ports import (
    BudgetRepository,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageSummary,
    OfferRepository,
    PasswordHasher,
    SelectedModelRepository,
    SpendProvider,
    TokenClaims,
    TokenService,
    UserProfileRepository,
    UserRepository,
)
from app.domain.auth import User
from app.domain.budget import BudgetSettings
from app.domain.entities import Offer, UserProfile
from app.domain.errors import AuthenticationError
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


class InMemorySelectedModelRepository(SelectedModelRepository):
    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def get(self) -> str | None:
        return self.model

    def set(self, model: str) -> None:
        self.model = model


class FixedSpendProvider(SpendProvider):
    """Returns a fixed spend, records the start instant it was asked about, and counts
    how many times it was actually queried (so caching can be asserted)."""

    def __init__(self, amount: float) -> None:
        self.amount = amount
        self.requested_start: datetime | None = None
        self.calls = 0

    def spend_since(self, start: datetime) -> float:
        self.calls += 1
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


class FakeUserRepository(UserRepository):
    def __init__(self, users: list[User] | None = None) -> None:
        self._by_id: dict[str, User] = {}
        self._by_email: dict[str, User] = {}
        for user in users or []:
            self.add(user)

    def add(self, user: User) -> None:
        self._by_id[user.id] = user
        self._by_email[user.email] = user

    def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)


class FakePasswordHasher(PasswordHasher):
    """Deterministic, reversible stand-in for a real hasher: the 'hash' is just the
    plaintext with a marker prefix, so tests stay fast and assertions are obvious."""

    _PREFIX = "hashed:"

    def hash(self, plain: str) -> str:
        return f"{self._PREFIX}{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"{self._PREFIX}{plain}"


class FakeTokenService(TokenService):
    """Encodes claims as a plain `user_id:version` string so tests can issue and verify
    without real crypto. Unparseable tokens raise AuthenticationError, like the real one."""

    def issue(self, user_id: str, token_version: int) -> str:
        return f"{user_id}:{token_version}"

    def verify(self, token: str) -> TokenClaims:
        try:
            user_id, version = token.rsplit(":", 1)
            return TokenClaims(user_id=user_id, token_version=int(version))
        except ValueError as exc:
            raise AuthenticationError("malformed token") from exc


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
