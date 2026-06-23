from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.domain.entities import Offer, UserProfile
from app.domain.salary_calculator import representative_monthly_salary
from app.domain.sorting import SortBy, SortOrder


@dataclass(frozen=True)
class MatchCriteria:
    candidate: UserProfile
    min_score: float = 0.0
    location: str | None = None
    min_salary: float | None = None
    include_expired: bool = False
    level: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OfferBrowseFilters:
    location: str | None = None
    min_salary: float | None = None
    tech: list[str] = field(default_factory=list)
    search: str | None = None
    include_expired: bool = False
    level: list[str] = field(default_factory=list)
    sort_by: SortBy | None = None
    sort_order: SortOrder = "desc"


def location_matches(offer: Offer, location: str | None) -> bool:
    if not location:
        return True
    wanted = location.casefold()
    return any(wanted in offer_location.casefold() for offer_location in offer.locations)


def tech_stack_matches(offer: Offer, techs: list[str]) -> bool:
    if not techs:
        return True
    offer_skills = [s.casefold() for s in (*offer.tech_stack, *offer.tech_stack_nice_to_have)]
    return all(
        any(wanted in skill for skill in offer_skills)
        for wanted in (t.casefold() for t in techs)
    )


def level_matches(offer: Offer, levels: list[str]) -> bool:
    if not levels:
        return True
    offer_levels = {lvl.casefold() for lvl in offer.levels}
    return any(wanted.casefold() in offer_levels for wanted in levels)


def text_matches(offer: Offer, search: str | None) -> bool:
    if not search:
        return True
    wanted = search.casefold()
    return wanted in offer.title.casefold() or wanted in offer.company.casefold()


def expired_matches(offer: Offer, include_expired: bool) -> bool:
    return include_expired or not offer.expired


def salary_meets_minimum(offer: Offer, min_salary: float | None) -> bool:
    if min_salary is None:
        return True
    amount = representative_monthly_salary(offer)
    return amount is not None and amount >= min_salary


class OfferFilter(ABC):
    @abstractmethod
    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool: ...


class FilterChain(OfferFilter):
    """Composes multiple `OfferFilter`s; an offer passes only if all of them do."""

    def __init__(self, offer_filters: list[OfferFilter] | None = None) -> None:
        self._offer_filters = list(offer_filters or [])

    def add_filter(self, offer_filter: OfferFilter) -> None:
        self._offer_filters.append(offer_filter)

    def remove_filter(self, offer_filter: OfferFilter) -> None:
        self._offer_filters.remove(offer_filter)

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return all(f.passes(offer, criteria) for f in self._offer_filters)
