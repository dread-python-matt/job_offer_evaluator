import pytest

from app.application.ports import OfferRepository, UserProfileRepository
from app.application.use_cases import (
    GetUserProfileUseCase,
    MatchOffersUseCase,
    SaveUserProfileUseCase,
)
from app.domain.entities import Offer, Skill, UserProfile
from app.domain.matching import (
    FilterChain,
    MatchCriteria,
    MatchScore,
    OfferFilter,
    OfferScorer,
    ScoreComponent,
)
from app.infrastructure.offer_filters import LocationFilter, SalaryFilter, SkillFilter
from app.infrastructure.scoring_strategies import SkillBasedScorer


class FakeUserProfileRepository(UserProfileRepository):
    def __init__(self, profile: UserProfile | None = None) -> None:
        self.profile = profile

    def save(self, profile: UserProfile) -> None:
        self.profile = profile

    def load(self) -> UserProfile | None:
        return self.profile


class FakeOfferRepository(OfferRepository):
    def __init__(self, offers: list[Offer]) -> None:
        self.offers = offers

    def list_offers(self) -> list[Offer]:
        return self.offers


class FixedScoringStrategy(OfferScorer):
    def __init__(self, score: float) -> None:
        self._score = score

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        return MatchScore().with_component(
            ScoreComponent(name="fixed", value=self._score, weight=1.0)
        )


class RejectAllOfferFilter(OfferFilter):
    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return False


def _profile(*skill_names: str) -> UserProfile:
    return UserProfile(
        summary="",
        skills=[Skill(name=name, rating=3) for name in skill_names],
        projects=[],
        experience=[],
    )


def test_save_user_profile_use_case_persists_profile_via_repository():
    repository = FakeUserProfileRepository()
    profile = _profile("Python")
    use_case = SaveUserProfileUseCase(repository)

    use_case.execute(profile)

    assert repository.load() == profile


def test_get_user_profile_use_case_returns_saved_profile():
    profile = _profile("Python")
    repository = FakeUserProfileRepository(profile)
    use_case = GetUserProfileUseCase(repository)

    assert use_case.execute() == profile


def test_get_user_profile_use_case_returns_none_when_no_profile_saved():
    repository = FakeUserProfileRepository(None)
    use_case = GetUserProfileUseCase(repository)

    assert use_case.execute() is None


def test_match_offers_use_case_filters_by_minimum_score_and_sorts_descending():
    candidate = _profile("Python", "FastAPI", "Docker")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python", "Java"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python", "FastAPI", "Docker"]),
        Offer(link="c", title="C", company="C", tech_stack=["Java"]),
    ]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, min_score=0.2), offers_limit=10
    )

    assert [r.offer.link for r in results] == ["b", "a"]
    assert results[0].score == pytest.approx(0.6)
    assert results[1].score == pytest.approx(0.3)


def test_match_offers_use_case_respects_offers_limit():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=1)

    assert len(results) == 1


def test_match_offers_use_case_returns_all_matches_when_offers_limit_is_none():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=None)

    assert len(results) == 2


def test_match_offers_use_case_returns_empty_when_no_offers_available():
    candidate = _profile("Python")
    use_case = MatchOffersUseCase(FakeOfferRepository([]), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=10)

    assert results == []


def test_match_offers_use_case_uses_injected_scoring_strategy():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Java"])]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), FixedScoringStrategy(0.42), FilterChain([SkillFilter()])
    )

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=10)

    assert results[0].score == pytest.approx(0.42)


def test_match_offers_use_case_uses_injected_offer_filter_to_exclude_offers_before_scoring():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([RejectAllOfferFilter()])
    )

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=10)

    assert results == []


def test_match_offers_use_case_filters_by_location():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], locations=["Warsaw"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], locations=["Berlin"]),
    ]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter(), LocationFilter()])
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, location="warsaw"), offers_limit=10
    )

    assert [r.offer.link for r in results] == ["a"]


def test_match_offers_use_case_filters_by_minimum_salary():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], salary_range="20000 - 25000 PLN/month"),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], salary_range="5000 - 6000 PLN/month"),
    ]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter(), SalaryFilter()])
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, min_salary=20000), offers_limit=10
    )

    assert [r.offer.link for r in results] == ["a"]
