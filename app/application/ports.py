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
    def get_summary(self) -> list[ModelUsageSummary]: ...


class ModelLimitsRegistry(ABC):
    @abstractmethod
    def get_limits(self, model: str) -> ModelLimits | None: ...


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
    """Reads actual money spent since a given instant. Raises CostUnavailableError
    when the figure can't be retrieved."""

    @abstractmethod
    def spend_since(self, start: datetime) -> float: ...


class BudgetRepository(ABC):
    """Persists the single budget configuration. `load` returns the stored settings,
    lazily initialising defaults on first use so it always returns a value."""

    @abstractmethod
    def load(self) -> BudgetSettings: ...

    @abstractmethod
    def save(self, settings: BudgetSettings) -> None: ...


class BudgetStatusReader(ABC):
    """Exposes the current budget status to consumers (e.g. the AI match gate) that
    only need to read it, not change it."""

    @abstractmethod
    def status(self) -> BudgetStatus: ...


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
