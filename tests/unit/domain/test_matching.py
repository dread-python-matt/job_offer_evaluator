import pytest

from app.domain.entities import Offer, Salary, UserProfile
from app.domain.filters import FilterChain, MatchCriteria, OfferFilter
from app.domain.scoring import MatchedOffer, MatchScore, ScoreComponent
from app.domain.sorting import sort_matched_offers, sort_offers


def test_overall_score_is_zero_with_no_components():
    assert MatchScore().overall_score == 0.0


def test_metadata_returns_value_stored_on_a_component():
    score = MatchScore().with_component(
        ScoreComponent(name="description", value=0.8, weight=1.0, metadata={"note": "hello"})
    )

    assert score.metadata("note") == "hello"


def test_metadata_returns_none_when_key_is_absent():
    score = MatchScore().with_component(ScoreComponent(name="skills", value=0.5, weight=1.0))

    assert score.metadata("missing") is None


def test_overall_score_is_the_weighted_average_of_its_components():
    score = (
        MatchScore()
        .with_component(ScoreComponent(name="skills", value=1.0, weight=4.0))
        .with_component(ScoreComponent(name="description", value=0.5, weight=1.0))
    )

    assert score.overall_score == pytest.approx((1.0 * 4 + 0.5 * 1) / 5)


def test_with_component_replaces_an_existing_component_with_the_same_name():
    score = (
        MatchScore()
        .with_component(ScoreComponent(name="skills", value=0.2, weight=1.0))
        .with_component(ScoreComponent(name="skills", value=0.8, weight=1.0))
    )

    assert score.get("skills") == 0.8
    assert len(score.components) == 1


def test_get_returns_none_for_a_missing_component():
    assert MatchScore().get("skills") is None


class _FixedFilter(OfferFilter):
    def __init__(self, result: bool) -> None:
        self._result = result

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return self._result


def _candidate() -> UserProfile:
    return UserProfile(summary="", skills=[], projects=[], experience=[])


def _criteria() -> MatchCriteria:
    return MatchCriteria(candidate=_candidate())


def _offer() -> Offer:
    return Offer(link="https://example.com", title="Dev", company="Acme")


def test_filter_chain_passes_when_it_has_no_filters():
    assert FilterChain().passes(_offer(), _criteria()) is True


def test_filter_chain_passes_only_when_all_filters_pass():
    chain = FilterChain([_FixedFilter(True), _FixedFilter(True)])

    assert chain.passes(_offer(), _criteria()) is True


def test_filter_chain_fails_when_any_filter_fails():
    chain = FilterChain([_FixedFilter(True), _FixedFilter(False)])

    assert chain.passes(_offer(), _criteria()) is False


def test_add_filter_appends_a_filter_to_the_chain():
    chain = FilterChain([_FixedFilter(True)])
    chain.add_filter(_FixedFilter(False))

    assert chain.passes(_offer(), _criteria()) is False


def test_remove_filter_removes_a_filter_from_the_chain():
    failing_filter = _FixedFilter(False)
    chain = FilterChain([_FixedFilter(True), failing_filter])

    chain.remove_filter(failing_filter)

    assert chain.passes(_offer(), _criteria()) is True


def _matched(link: str, score: float, salary: Salary | None = None, published: str | None = None) -> MatchedOffer:
    offer = Offer(
        link=link,
        title="Dev",
        company="Acme",
        salaries=[salary] if salary else [],
        published=published,
    )
    return MatchedOffer(offer=offer, score=score, matched_skills=set())


def test_sort_matched_offers_sorts_by_score_descending_by_default():
    matches = [_matched("a", 0.2), _matched("b", 0.9)]

    sorted_matches = sort_matched_offers(matches, "score", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_sorts_by_score_ascending_when_requested():
    matches = [_matched("a", 0.9), _matched("b", 0.2)]

    sorted_matches = sort_matched_offers(matches, "score", "asc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_sorts_by_salary():
    matches = [
        _matched("a", 0.5, salary=Salary("permanent", 5000, 6000, "PLN", "month", net_mid=5500)),
        _matched("b", 0.5, salary=Salary("permanent", 20000, 25000, "PLN", "month", net_mid=22500)),
    ]

    sorted_matches = sort_matched_offers(matches, "salary_mid", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_sorts_offers_missing_salary_last():
    matches = [
        _matched("a", 0.5),
        _matched("b", 0.5, salary=Salary("permanent", 20000, 25000, "PLN", "month", net_mid=22500)),
    ]

    sorted_matches = sort_matched_offers(matches, "salary_mid", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_sorts_by_recent():
    matches = [
        _matched("a", 0.5, published="2026-05-01"),
        _matched("b", 0.5, published="2026-06-10"),
    ]

    sorted_matches = sort_matched_offers(matches, "recent", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_score_recent_sorts_by_score_primarily():
    matches = [_matched("a", 0.3, published="2026-06-20"), _matched("b", 0.9, published="2026-01-01")]

    sorted_matches = sort_matched_offers(matches, "score_recent", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_score_recent_breaks_ties_by_recency():
    matches = [
        _matched("a", 0.7, published="2026-05-01"),
        _matched("b", 0.7, published="2026-06-10"),
    ]

    sorted_matches = sort_matched_offers(matches, "score_recent", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_score_recent_puts_missing_published_last_on_tie():
    matches = [
        _matched("a", 0.7),
        _matched("b", 0.7, published="2026-06-10"),
    ]

    sorted_matches = sort_matched_offers(matches, "score_recent", "desc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


def test_sort_matched_offers_score_recent_puts_missing_published_last_on_tie_ascending():
    matches = [
        _matched("a", 0.7),
        _matched("b", 0.7, published="2026-06-10"),
    ]

    sorted_matches = sort_matched_offers(matches, "score_recent", "asc")

    assert [m.offer.link for m in sorted_matches] == ["b", "a"]


# --- sort_offers ---


def _simple_offer(link: str, salary: Salary | None = None, published: str | None = None) -> Offer:
    return Offer(
        link=link,
        title="Dev",
        company="Acme",
        salaries=[salary] if salary else [],
        published=published,
    )


def test_sort_offers_with_no_sort_by_defaults_to_recent_desc():
    offers = [
        _simple_offer("a", published="2026-01-01"),
        _simple_offer("b", published="2026-06-10"),
    ]

    result = sort_offers(offers, sort_by=None)

    assert [o.link for o in result] == ["b", "a"]


def test_sort_offers_with_no_sort_by_respects_asc_order():
    offers = [
        _simple_offer("b", published="2026-06-10"),
        _simple_offer("a", published="2026-01-01"),
    ]

    result = sort_offers(offers, sort_by=None, sort_order="asc")

    assert [o.link for o in result] == ["a", "b"]


def test_sort_offers_with_no_sort_by_places_undated_offers_last():
    offers = [
        _simple_offer("a"),
        _simple_offer("b", published="2026-06-10"),
    ]

    result = sort_offers(offers, sort_by=None)

    assert [o.link for o in result] == ["b", "a"]


def test_sort_offers_sorts_by_salary_descending():
    offers = [
        _simple_offer("a", salary=Salary("permanent", 5000, 6000, "PLN", "month", net_mid=5500)),
        _simple_offer("b", salary=Salary("permanent", 20000, 25000, "PLN", "month", net_mid=22500)),
        _simple_offer("c", salary=Salary("permanent", 10000, 12000, "PLN", "month", net_mid=11000)),
    ]

    result = sort_offers(offers, sort_by="salary_mid", sort_order="desc")

    assert [o.link for o in result] == ["b", "c", "a"]


def test_sort_offers_sorts_by_salary_ascending():
    offers = [
        _simple_offer("a", salary=Salary("permanent", 10000, 12000, "PLN", "month", net_mid=11000)),
        _simple_offer("b", salary=Salary("permanent", 5000, 6000, "PLN", "month", net_mid=5500)),
    ]

    result = sort_offers(offers, sort_by="salary_mid", sort_order="asc")

    assert [o.link for o in result] == ["b", "a"]


def test_sort_offers_places_offers_without_salary_last():
    offers = [
        _simple_offer("a"),
        _simple_offer("b", salary=Salary("permanent", 20000, 25000, "PLN", "month", net_mid=22500)),
    ]

    result = sort_offers(offers, sort_by="salary_mid", sort_order="desc")

    assert [o.link for o in result] == ["b", "a"]


def test_sort_offers_sorts_by_recent_descending():
    offers = [
        _simple_offer("a", published="2026-05-01"),
        _simple_offer("b", published="2026-06-10"),
    ]

    result = sort_offers(offers, sort_by="recent", sort_order="desc")

    assert [o.link for o in result] == ["b", "a"]


def test_sort_offers_places_offers_without_published_date_last():
    offers = [
        _simple_offer("a"),
        _simple_offer("b", published="2026-06-10"),
    ]

    result = sort_offers(offers, sort_by="recent", sort_order="desc")

    assert [o.link for o in result] == ["b", "a"]
