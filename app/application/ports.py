from abc import ABC, abstractmethod

from app.domain.entities import Offer, UserProfile


class UserProfileRepository(ABC):
    @abstractmethod
    def save(self, profile: UserProfile) -> None: ...

    @abstractmethod
    def load(self) -> UserProfile | None: ...


class OfferRepository(ABC):
    @abstractmethod
    def list_offers(self) -> list[Offer]: ...
