from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities import Offer, UserProfile


@dataclass(frozen=True)
class Score:
    skills_score: float
    description_score: float

    @property
    def overall_score(self) -> float:
        return ((self.skills_score * 4 + self.description_score) / 5) / 2


@dataclass(frozen=True)
class MatchedOffer:
    offer: Offer
    score: float
    matched_skills: set[str]


class ScoringStrategy(ABC):
    @abstractmethod
    def score(self, candidate: UserProfile, offer: Offer) -> Score: ...
