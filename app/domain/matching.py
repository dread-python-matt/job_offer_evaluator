from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from app.domain.entities import Offer, Salary, UserProfile

SortBy = Literal["salary", "recent"]
MatchSortBy = Literal["score", "salary", "recent", "score_recent"]
SortOrder = Literal["asc", "desc"]


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

        return MatchScore(
            components=components + (component,)
        )

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
            component.value * component.weight
            for component in self.components
        ) / total_weight


class OfferScorer(ABC):
    @abstractmethod
    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore: ...


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
    """True when no location was requested, or the requested text appears
    (case-insensitively) in at least one of the offer's locations."""
    if not location:
        return True
    wanted = location.casefold()
    return any(wanted in offer_location.casefold() for offer_location in offer.locations)


def tech_stack_matches(offer: Offer, techs: list[str]) -> bool:
    """True when no techs were requested, or ALL requested techs appear
    (case-insensitive substring match) in the offer's required or nice-to-have stack."""
    if not techs:
        return True
    offer_skills = [s.casefold() for s in (*offer.tech_stack, *offer.tech_stack_nice_to_have)]
    return all(
        any(wanted in skill for skill in offer_skills)
        for wanted in (t.casefold() for t in techs)
    )


def level_matches(offer: Offer, levels: list[str]) -> bool:
    """True when no levels were requested, or ANY of the requested levels matches
    (case-insensitive exact match) among the offer's levels."""
    if not levels:
        return True
    offer_levels = {lvl.casefold() for lvl in offer.levels}
    return any(wanted.casefold() in offer_levels for wanted in levels)


def text_matches(offer: Offer, search: str | None) -> bool:
    """True when no search text was requested, or it appears (case-insensitively) in
    the offer's title or company name."""
    if not search:
        return True
    wanted = search.casefold()
    return wanted in offer.title.casefold() or wanted in offer.company.casefold()


_HOURS_PER_MONTH = 168
_DAYS_PER_MONTH = 21
_MONTHS_PER_YEAR = 12

_MONTHLY_FACTOR_BY_PERIOD = {
    "month": 1.0,
    "hour": float(_HOURS_PER_MONTH),
    "day": float(_DAYS_PER_MONTH),
    "year": 1.0 / _MONTHS_PER_YEAR,
}


def representative_monthly_salary(offer: Offer) -> float | None:
    """The offer's best (highest) salary entry normalized to a monthly amount, or
    `None` if it has no salary entries whose period can be normalized."""
    monthly_amounts = [
        amount for salary in offer.salaries if (amount := monthly_gross_amount(salary)) is not None
    ]
    return max(monthly_amounts) if monthly_amounts else None


def salary_meets_minimum(offer: Offer, min_salary: float | None) -> bool:
    """True when no minimum salary was requested, or the offer's
    `representative_monthly_salary` meets it. Offers with no salary entries, or whose
    period can't be normalized (e.g. an unknown/blank `period`), are excluded when a
    minimum is requested, since we can't confirm they meet it."""
    if min_salary is None:
        return True
    amount = representative_monthly_salary(offer)
    return amount is not None and amount >= min_salary


def monthly_gross_amount(salary: Salary) -> float | None:
    """A salary entry's amount normalized to a monthly gross figure, or `None` if its
    `period` can't be normalized (e.g. unknown/blank)."""
    amount = salary.max_amount if salary.max_amount is not None else salary.min_amount
    if amount is None:
        return None
    factor = _MONTHLY_FACTOR_BY_PERIOD.get(salary.period)
    if factor is None:
        return None
    return amount * factor


def expired_matches(offer: Offer, include_expired: bool) -> bool:
    """True when expired offers were explicitly requested, or the offer isn't expired."""
    return include_expired or not offer.expired


def offer_sort_key(offer: Offer, sort_by: SortBy) -> float | str | None:
    """The value an offer is ranked by for a given `sort_by` feature."""
    if sort_by == "salary":
        return representative_monthly_salary(offer)
    return offer.published


def sort_offers(
    offers: list[Offer], sort_by: SortBy | None, sort_order: SortOrder = "desc"
) -> list[Offer]:
    """Sorts offers by `sort_by` ("salary" or "recent"); offers missing that value are
    placed last regardless of `sort_order`. A `None` `sort_by` leaves the list as-is."""
    if sort_by is None:
        return offers

    def key(offer: Offer) -> float | str:
        return offer_sort_key(offer, sort_by)

    with_value = [offer for offer in offers if key(offer) is not None]
    without_value = [offer for offer in offers if key(offer) is None]
    with_value.sort(key=key, reverse=(sort_order == "desc"))
    return with_value + without_value


def sort_matched_offers(
    matched_offers: list[MatchedOffer], sort_by: MatchSortBy, sort_order: SortOrder = "desc"
) -> list[MatchedOffer]:
    """Sorts `MatchedOffer`s by `sort_by` ("score", "salary" or "recent"); offers missing
    that value (only possible for "salary"/"recent") are placed last regardless of
    `sort_order`."""
    reverse = sort_order == "desc"
    if sort_by == "score":
        return sorted(matched_offers, key=lambda m: m.score, reverse=reverse)

    if sort_by == "score_recent":
        return sorted(
            matched_offers,
            key=lambda m: (m.score, m.offer.published or ""),
            reverse=reverse,
        )

    def key(matched: MatchedOffer) -> float | str | None:
        return offer_sort_key(matched.offer, sort_by)

    with_value = [m for m in matched_offers if key(m) is not None]
    without_value = [m for m in matched_offers if key(m) is None]
    with_value.sort(key=key, reverse=reverse)
    return with_value + without_value


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
        return all(
            offer_filter.passes(offer, criteria)
            for offer_filter in self._offer_filters
        )
