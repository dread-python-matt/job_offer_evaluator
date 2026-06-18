import pytest

from app.domain.entities import Offer, UserProfile
from app.domain.matching import FilterChain, MatchCriteria, MatchScore, OfferFilter, ScoreComponent


def test_overall_score_is_zero_with_no_components():
    assert MatchScore().overall_score == 0.0


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
