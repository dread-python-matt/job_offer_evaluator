from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities import Offer, UserProfile


@dataclass(frozen=True)
class MatchedOffer:
    offer: Offer
    score: float
    matched_skills: set[str]


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
