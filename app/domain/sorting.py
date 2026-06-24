from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from app.domain.entities import Offer

if TYPE_CHECKING:
    from app.domain.scoring import MatchedOffer

SortBy = Literal["recent", "salary_min", "salary_mid", "salary_max"]
MatchSortBy = Literal["score", "recent", "score_recent", "salary_min", "salary_mid", "salary_max"]
SortOrder = Literal["asc", "desc"]

# Salary sort keys -> the net bound they rank by.
SALARY_SORT_BOUNDS: dict[str, str] = {
    "salary_min": "min",
    "salary_mid": "mid",
    "salary_max": "max",
}


def offer_sort_key(offer: Offer, sort_by: SortBy) -> float | str | None:
    from app.domain.salary_calculator import representative_net

    bound = SALARY_SORT_BOUNDS.get(sort_by)
    if bound is not None:
        return representative_net(offer, bound)
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
    from app.domain.salary_calculator import representative_net

    date_sentinel = "" if reverse else "z"

    match sort_by:
        case "score":
            return lambda m: m.score
        case "score_recent":
            return lambda m: (m.score, m.offer.published or date_sentinel)
        case "recent":
            return lambda m: m.offer.published or date_sentinel
        case _:  # salary_min | salary_mid | salary_max
            bound = SALARY_SORT_BOUNDS[sort_by]
            none_sentinel: float = float("-inf") if reverse else float("inf")
            def _salary_key(m: "MatchedOffer", _s: float = none_sentinel, _b: str = bound) -> float:
                amt = representative_net(m.offer, _b)
                return amt if amt is not None else _s
            return _salary_key


def sort_matched_offers(
    matched_offers: list["MatchedOffer"], sort_by: MatchSortBy, sort_order: SortOrder = "desc"
) -> list["MatchedOffer"]:
    reverse = sort_order == "desc"
    return sorted(matched_offers, key=_build_match_sort_key(sort_by, reverse), reverse=reverse)
