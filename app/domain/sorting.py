from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from app.domain.entities import Offer

if TYPE_CHECKING:
    from app.domain.scoring import MatchedOffer

SortBy = Literal["salary", "recent"]
MatchSortBy = Literal["score", "salary", "recent", "score_recent"]
SortOrder = Literal["asc", "desc"]


def offer_sort_key(offer: Offer, sort_by: SortBy) -> float | str | None:
    from app.domain.salary_calculator import representative_monthly_salary

    if sort_by == "salary":
        return representative_monthly_salary(offer)
    return offer.published


def sort_offers(
    offers: list[Offer], sort_by: SortBy | None, sort_order: SortOrder = "desc"
) -> list[Offer]:
    """Sort offers by `sort_by`, defaulting to "recent" when omitted so that
    `sort_order` is always respected. Offers missing the sort value are placed last
    regardless of `sort_order`."""
    effective_sort: SortBy = sort_by or "recent"

    def key(offer: Offer) -> float | str | None:
        return offer_sort_key(offer, effective_sort)

    with_value = [offer for offer in offers if key(offer) is not None]
    without_value = [offer for offer in offers if key(offer) is None]
    with_value.sort(key=key, reverse=(sort_order == "desc"))
    return with_value + without_value


def _build_match_sort_key(sort_by: MatchSortBy, reverse: bool) -> Callable[["MatchedOffer"], Any]:
    """Return a sort-key function for the given sort mode and direction.

    None-valued items are always placed last via a direction-aware sentinel so that
    a single sorted() call handles both the "has value" and "no value" cases."""
    from app.domain.salary_calculator import representative_monthly_salary

    date_sentinel = "" if reverse else "z"

    match sort_by:
        case "score":
            return lambda m: m.score
        case "score_recent":
            return lambda m: (m.score, m.offer.published or date_sentinel)
        case "recent":
            return lambda m: m.offer.published or date_sentinel
        case "salary":
            none_sentinel: float = float("-inf") if reverse else float("inf")
            def _salary_key(m: "MatchedOffer", _s: float = none_sentinel) -> float:
                amt = representative_monthly_salary(m.offer)
                return amt if amt is not None else _s
            return _salary_key


def sort_matched_offers(
    matched_offers: list["MatchedOffer"], sort_by: MatchSortBy, sort_order: SortOrder = "desc"
) -> list["MatchedOffer"]:
    reverse = sort_order == "desc"
    return sorted(matched_offers, key=_build_match_sort_key(sort_by, reverse), reverse=reverse)
