from dataclasses import replace
from datetime import datetime

from app.application.ports import (
    BudgetRepository,
    EmailSender,
    EmailValidator,
    ModelUsage,
    ModelUsageRepository,
    ModelUsageSummary,
    OfferRepository,
    PasswordHasher,
    PasswordResetTokenService,
    SelectedModelRepository,
    SpendProvider,
    TokenClaims,
    TokenService,
    UserProfileRepository,
    UserRepository,
    UserSpendProvider,
    VerificationTokenService,
)
from app.domain.auth import User
from app.domain.budget import BudgetSettings
from app.domain.entities import Offer, UserProfile
from app.domain.errors import (
    AuthenticationError,
    InvalidPasswordResetTokenError,
    InvalidVerificationTokenError,
)
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
    """Per-user budgets, lazily defaulting to the seed `default` until a user saves."""

    def __init__(self, default: BudgetSettings) -> None:
        self._default = default
        self._by_user: dict[str, BudgetSettings] = {}

    def load(self, user_id: str) -> BudgetSettings:
        return self._by_user.get(user_id, self._default)

    def save(self, user_id: str, settings: BudgetSettings) -> None:
        self._by_user[user_id] = settings


class FixedUserSpendProvider(UserSpendProvider):
    """Returns a fixed per-user spend and records what it was asked about (so caching
    and per-user behaviour can be asserted)."""

    def __init__(self, amount: float) -> None:
        self.amount = amount
        self.requested_start: datetime | None = None
        self.requested_user: str | None = None
        self.calls = 0

    def spend_since(self, user_id: str, start: datetime) -> float:
        self.calls += 1
        self.requested_start = start
        self.requested_user = user_id
        return self.amount


class InMemorySelectedModelRepository(SelectedModelRepository):
    """In-memory per-user model selection. A single seed `model` is stored under
    `seed_user_id` for convenience, matching the fake user used by the API tests."""

    def __init__(self, model: str | None = None, seed_user_id: str = "user-1") -> None:
        self._models: dict[str, str] = {}
        if model is not None:
            self._models[seed_user_id] = model

    def get(self, user_id: str) -> str | None:
        return self._models.get(user_id)

    def set(self, user_id: str, model: str) -> None:
        self._models[user_id] = model


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
    """In-memory per-user profiles. For convenience a single seed `profile` is stored
    under `seed_user_id`, matching the fake user used by the API tests."""

    def __init__(self, profile: UserProfile | None = None, seed_user_id: str = "user-1") -> None:
        self._profiles: dict[str, UserProfile] = {}
        if profile is not None:
            self._profiles[seed_user_id] = profile

    def save(self, user_id: str, profile: UserProfile) -> None:
        self._profiles[user_id] = profile

    def load(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)


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

    def get_summary(self, user_id: str) -> list[ModelUsageSummary]:
        # Tests seed a fixed summary list; the user filter is exercised in integration.
        return self._summaries

    def usage_since(self, user_id: str, start) -> list[ModelUsageSummary]:
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

    def mark_email_verified(self, user_id: str) -> None:
        user = self._by_id.get(user_id)
        if user is not None:
            self.add(replace(user, email_verified=True))

    def update_password(self, user_id: str, password_hash: str, token_version: int) -> None:
        user = self._by_id.get(user_id)
        if user is not None:
            self.add(replace(user, password_hash=password_hash, token_version=token_version))


class FakeEmailValidator(EmailValidator):
    """Reports a fixed deliverability verdict so the registration use case can be tested
    without DNS. Defaults to deliverable; flip `deliverable` to exercise rejection."""

    def __init__(self, deliverable: bool = True) -> None:
        self.deliverable = deliverable
        self.checked: list[str] = []

    def is_deliverable(self, email: str) -> bool:
        self.checked.append(email)
        return self.deliverable


class FakeEmailSender(EmailSender):
    """Captures sent emails in memory so tests can assert what was sent (and read the
    confirmation link out of the body)."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


class FakeVerificationTokenService(VerificationTokenService):
    """Encodes the user id as a `verify:<user_id>` string so tests can issue and verify
    confirmation tokens without crypto. Anything else raises, like the real adapter."""

    _PREFIX = "verify:"

    def issue(self, user_id: str) -> str:
        return f"{self._PREFIX}{user_id}"

    def verify(self, token: str) -> str:
        if not token.startswith(self._PREFIX):
            raise InvalidVerificationTokenError("malformed verification token")
        return token[len(self._PREFIX) :]


class FakePasswordResetTokenService(PasswordResetTokenService):
    """Encodes the user id as a `reset:<user_id>` string so tests can issue and verify
    reset tokens without crypto. Anything else raises, like the real adapter."""

    _PREFIX = "reset:"

    def issue(self, user_id: str) -> str:
        return f"{self._PREFIX}{user_id}"

    def verify(self, token: str) -> str:
        if not token.startswith(self._PREFIX):
            raise InvalidPasswordResetTokenError("malformed reset token")
        return token[len(self._PREFIX) :]


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
