from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities import Offer, UserProfile


@dataclass(frozen=True)
class AiInsight:
    """The model's qualitative explanation behind an AI fit score."""

    rate: int
    pros: list[str]
    cons: list[str]
    rate_reason: str


@dataclass(frozen=True)
class MatchedOffer:
    offer: Offer
    score: float
    matched_skills: set[str]
    ai_insight: AiInsight | None = None


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    value: float
    weight: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchScore:
    components: tuple[ScoreComponent, ...] = ()

    def with_component(self, component: ScoreComponent) -> "MatchScore":
        components = tuple(
            existing
            for existing in self.components
            if existing.name != component.name
        )
        return MatchScore(components=components + (component,))

    def get(self, name: str) -> float | None:
        for component in self.components:
            if component.name == name:
                return component.value
        return None

    def metadata(self, key: str) -> Any | None:
        """Return the first component metadata value stored under `key`, or None.

        Lets scorers attach side-channel data (e.g. an AI explanation) to a
        component without widening the scorer return type."""
        for component in self.components:
            if key in component.metadata:
                return component.metadata[key]
        return None

    @property
    def overall_score(self) -> float:
        total_weight = sum(component.weight for component in self.components)
        if total_weight == 0:
            return 0.0
        return sum(
            component.value * component.weight for component in self.components
        ) / total_weight


class OfferScorer(ABC):
    @abstractmethod
    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore: ...

    async def score_async(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        """Async variant used by the parallel match use case. The default just runs
        the synchronous `score`, which is correct for in-memory/deterministic scorers.
        I/O-bound scorers (e.g. LLM-backed) override this with a truly awaitable
        implementation so many offers can be scored concurrently."""
        return self.score(candidate, offer)
