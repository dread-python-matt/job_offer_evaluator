from typing import TYPE_CHECKING, Literal

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


def sort_matched_offers(
    matched_offers: list["MatchedOffer"], sort_by: MatchSortBy, sort_order: SortOrder = "desc"
) -> list["MatchedOffer"]:
    reverse = sort_order == "desc"
    if sort_by == "score":
        return sorted(matched_offers, key=lambda m: m.score, reverse=reverse)

    if sort_by == "score_recent":
        # For DESC (reverse=True): "" < any ISO date, so None-published sorts last within score group.
        # For ASC (reverse=False): "z" > any ISO date digit, so None-published sorts last within score group.
        published_sentinel = "" if reverse else "z"
        return sorted(
            matched_offers,
            key=lambda m: (m.score, m.offer.published or published_sentinel),
            reverse=reverse,
        )

    def key(matched: "MatchedOffer") -> float | str | None:
        return offer_sort_key(matched.offer, sort_by)

    with_value = [m for m in matched_offers if key(m) is not None]
    without_value = [m for m in matched_offers if key(m) is None]
    with_value.sort(key=key, reverse=reverse)
    return with_value + without_value
