from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.auth import User
from app.domain.budget import BudgetSettings, BudgetStatus
from app.domain.entities import Offer, UserProfile
from app.domain.scoring import MatchScore

if TYPE_CHECKING:
    from app.domain.filters import OfferBrowseFilters


class UserProfileRepository(ABC):
    @abstractmethod
    def save(self, user_id: str, profile: UserProfile) -> None: ...

    @abstractmethod
    def load(self, user_id: str) -> UserProfile | None: ...


class OfferRepository(ABC):
    @abstractmethod
    def list_offers(self) -> list[Offer]: ...

    @abstractmethod
    def count_offers(self) -> int: ...

    @abstractmethod
    def browse_offers(
        self, filters: "OfferBrowseFilters", limit: int, offset: int
    ) -> tuple[list[Offer], int]: ...


@dataclass(frozen=True)
class ModelUsage:
    label: str
    input_tokens: int
    output_tokens: int
    model: str = ""
    company: str = ""
    user_id: str = ""


class ModelUsageTracker(ABC):
    @abstractmethod
    def record(self, usage: ModelUsage) -> None: ...

    @abstractmethod
    def flush(self) -> list[ModelUsage]: ...


class InMemoryModelUsageTracker(ModelUsageTracker):
    def __init__(self) -> None:
        self._records: list[ModelUsage] = []

    def record(self, usage: ModelUsage) -> None:
        self._records.append(usage)

    def flush(self) -> list[ModelUsage]:
        records = list(self._records)
        self._records.clear()
        return records


@dataclass(frozen=True)
class ModelLimits:
    rpm: int
    tpm: int
    rpd: int


@dataclass(frozen=True)
class ModelUsageSummary:
    company: str
    model: str
    input_tokens: int
    output_tokens: int


@dataclass
class ModelUsageWithLimits:
    company: str
    model: str
    input_tokens: int
    output_tokens: int
    limits: ModelLimits | None


class ModelUsageRepository(ABC):
    @abstractmethod
    def save(self, usage: ModelUsage) -> None: ...

    @abstractmethod
    def get_summary(self, user_id: str) -> list[ModelUsageSummary]: ...

    @abstractmethod
    def usage_since(self, user_id: str, start: datetime) -> list[ModelUsageSummary]:
        """Per-model token totals for a user since `start` (used for budget accounting)."""


class ModelLimitsRegistry(ABC):
    @abstractmethod
    def get_limits(self, model: str) -> ModelLimits | None: ...


@dataclass(frozen=True)
class ModelPrice:
    """USD price per 1,000,000 tokens, split by input vs output."""

    input_per_million: float
    output_per_million: float


class ModelPricingRegistry(ABC):
    @abstractmethod
    def get_price(self, model: str) -> ModelPrice | None: ...


class ExternalUsageProvider(ABC):
    @abstractmethod
    def get_today_usage(self) -> list[ModelUsageSummary]: ...


@dataclass(frozen=True)
class AvailableModel:
    model: str
    company: str


class AvailableModelsProvider(ABC):
    @abstractmethod
    def list_models(self) -> list[AvailableModel]: ...


class SpendProvider(ABC):
    """Reads actual money spent (org-wide) since a given instant. Raises
    CostUnavailableError when the figure can't be retrieved. Used for the global
    spend backstop; it cannot be attributed per user."""

    @abstractmethod
    def spend_since(self, start: datetime) -> float: ...


class UserSpendProvider(ABC):
    """Computes how much a single user has spent since a given instant. The token
    accounting implementation derives this from the user's recorded model usage."""

    @abstractmethod
    def spend_since(self, user_id: str, start: datetime) -> float: ...


class BudgetRepository(ABC):
    """Persists each user's budget configuration. `load` returns the stored settings,
    lazily initialising defaults on first use so it always returns a value."""

    @abstractmethod
    def load(self, user_id: str) -> BudgetSettings: ...

    @abstractmethod
    def save(self, user_id: str, settings: BudgetSettings) -> None: ...


class BudgetStatusReader(ABC):
    """Exposes a user's current budget status to consumers (e.g. the AI match gate)
    that only need to read it, not change it."""

    @abstractmethod
    def status(self, user_id: str) -> BudgetStatus: ...


class AiScoreCacheRepository(ABC):
    """Caches AI scores by a content key so identical (model, candidate, offer) scoring
    isn't re-paid for. `get` returns None on a miss."""

    @abstractmethod
    def get(self, key: str) -> MatchScore | None: ...

    @abstractmethod
    def put(self, key: str, score: MatchScore) -> None: ...


class SelectedModelRepository(ABC):
    """Persists each user's selected scoring model so it's shared across processes/workers
    and survives restarts. `get` returns None when that user has not selected one yet."""

    @abstractmethod
    def get(self, user_id: str) -> str | None: ...

    @abstractmethod
    def set(self, user_id: str, model: str) -> None: ...


class UserRepository(ABC):
    @abstractmethod
    def add(self, user: User) -> None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def mark_email_verified(self, user_id: str) -> None:
        """Flag the user's email as confirmed. Idempotent: marking an already-verified
        user again is a no-op."""

    @abstractmethod
    def update_password(self, user_id: str, password_hash: str, token_version: int) -> None:
        """Persist a new password hash and token_version for the user in a single write.
        Bumping token_version invalidates every previously issued session token."""


class EmailValidator(ABC):
    """Checks whether an address is actually usable beyond mere syntax (e.g. its domain
    can receive mail). Syntax is validated upstream by the request schema; this is the
    optional deliverability layer, isolated behind a port so it can be faked in tests."""

    @abstractmethod
    def is_deliverable(self, email: str) -> bool: ...


class EmailSender(ABC):
    """Sends a plain-text email. The transport (SMTP, console, a provider) is an
    infrastructure concern; use cases depend only on this port."""

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...


class RateLimiter(ABC):
    """Throttles repeated attempts identified by an opaque key (e.g. client-IP + email).
    The limiter only counts attempts within a window and reports when a key is over its
    allowance; deciding what counts as an attempt (and resetting on success) is the
    caller's responsibility."""

    @abstractmethod
    def check(self, key: str) -> None:
        """Raise `RateLimitExceededError` if `key` has reached its allowance in the current
        window. Read-only: a check does not itself count as an attempt."""

    @abstractmethod
    def record_failure(self, key: str) -> None:
        """Count one failed attempt against `key`."""

    @abstractmethod
    def reset(self, key: str) -> None:
        """Discard all recorded attempts for `key` (e.g. after a success)."""


class VerificationTokenService(ABC):
    """Issues and validates single-purpose email-confirmation tokens, kept separate from
    session tokens so the two can never be substituted for one another."""

    @abstractmethod
    def issue(self, user_id: str) -> str: ...

    @abstractmethod
    def verify(self, token: str) -> str:
        """Return the user id encoded in a confirmation token. Raises
        `InvalidVerificationTokenError` when the token is malformed, expired, has the
        wrong purpose, or has a bad signature."""


class PasswordResetTokenService(ABC):
    """Issues and validates single-purpose password-reset tokens, kept separate from session
    and email-confirmation tokens so none can be substituted for another."""

    @abstractmethod
    def issue(self, user_id: str) -> str: ...

    @abstractmethod
    def verify(self, token: str) -> str:
        """Return the user id encoded in a reset token. Raises
        `InvalidPasswordResetTokenError` when the token is malformed, expired, has the
        wrong purpose, or has a bad signature."""


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, plain: str) -> str: ...

    @abstractmethod
    def verify(self, plain: str, hashed: str) -> bool: ...


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    token_version: int


class TokenService(ABC):
    @abstractmethod
    def issue(self, user_id: str, token_version: int) -> str: ...

    @abstractmethod
    def verify(self, token: str) -> TokenClaims:
        """Decode and validate a session token. Raises `AuthenticationError` when the
        token is missing required claims, malformed, expired, or has a bad signature."""
