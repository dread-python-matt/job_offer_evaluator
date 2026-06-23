from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.entities import Offer, UserProfile

if TYPE_CHECKING:
    from app.domain.filters import OfferBrowseFilters


class UserProfileRepository(ABC):
    @abstractmethod
    def save(self, profile: UserProfile) -> None: ...

    @abstractmethod
    def load(self) -> UserProfile | None: ...


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
