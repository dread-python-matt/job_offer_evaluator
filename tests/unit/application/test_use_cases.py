import asyncio
from datetime import datetime, timezone

import pytest

from app.application.ports import BudgetStatusReader, ExternalUsageProvider, InMemoryModelUsageTracker, ModelUsage, ModelUsageSummary
from app.domain.budget import BudgetStatus
from app.domain.errors import AiScoringError, BudgetExceededError
from app.application.use_cases import (
    CalculateNetSalaryUseCase,
    GetModelUsageSummaryUseCase,
    CountOffersUseCase,
    GetUserProfileUseCase,
    ListOffersUseCase,
    MatchOffersUseCase,
    MatchOffersWithAiUseCase,
    SaveUserProfileUseCase,
)
from app.domain.salary_calculator import ContractType, SalaryCalculator
from app.domain.entities import Offer, Salary, Skill, UserProfile
from app.domain.filters import FilterChain, MatchCriteria, OfferBrowseFilters, OfferFilter
from app.domain.scoring import AiInsight, MatchScore, OfferScorer, ScoreComponent
from app.infrastructure.offer_filters import (
    ExpiredFilter,
    LevelFilter,
    LocationFilter,
    SalaryFilter,
    SkillFilter,
)
from app.infrastructure.scoring_strategies import SkillBasedScorer
from tests.fakes import (
    FakeModelUsageRepository,
    FakeOfferRepository,
    FakeUserProfileRepository,
    ScoreByLinkScorer,
)


def _salary(min_amount: float, max_amount: float, period: str = "month") -> Salary:
    # Net figures drive filtering/sorting now; use the gross numbers as stand-in net so
    # the relative ordering/threshold assertions still hold.
    return Salary(
        contract_type="permanent",
        min_amount=min_amount,
        max_amount=max_amount,
        currency="PLN",
        period=period,
        net_min=min_amount,
        net_mid=(min_amount + max_amount) / 2,
        net_max=max_amount,
    )


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


def test_match_offers_with_ai_use_case_excludes_offers_via_filter_chain_before_scoring():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    ranking_scorer = ScoreByLinkScorer({"a": 0.9})
    ai_scorer = ScoreByLinkScorer({"a": 0.9})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([RejectAllOfferFilter()]), ranking_scorer, ai_scorer
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10
    )

    assert results.matches == []
    assert ai_scorer.scored_links == []


def test_match_offers_with_ai_use_case_only_sends_top_ranked_offers_to_the_ai_scorer():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
        Offer(link="c", title="C", company="C", tech_stack=["Python"]),
    ]
    ranking_scorer = ScoreByLinkScorer({"a": 0.9, "b": 0.5, "c": 0.1})
    ai_scorer = ScoreByLinkScorer({"a": 0.1, "b": 0.1, "c": 0.1})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([]), ranking_scorer, ai_scorer
    )

    use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=2, offers_limit=10)

    assert sorted(ai_scorer.scored_links) == ["a", "b"]


def test_match_offers_with_ai_use_case_computes_matched_skills_locally():
    candidate = _profile("Python", "FastAPI")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python", "Java"])]
    ranking_scorer = ScoreByLinkScorer({"a": 0.9})
    ai_scorer = ScoreByLinkScorer({"a": 0.42})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([]), ranking_scorer, ai_scorer
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10
    )

    assert results.matches[0].score == pytest.approx(0.42)
    assert results.matches[0].matched_skills == {"python"}


def test_match_offers_with_ai_use_case_filters_final_results_by_ai_min_score():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    ranking_scorer = ScoreByLinkScorer({"a": 0.9, "b": 0.9})
    ai_scorer = ScoreByLinkScorer({"a": 0.8, "b": 0.1})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([]), ranking_scorer, ai_scorer
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate),
        offers_to_score=10,
        offers_limit=10,
        ai_min_score=0.5,
    )

    assert [r.offer.link for r in results.matches] == ["a"]


def test_match_offers_with_ai_criteria_min_score_does_not_filter_ai_results():
    """criteria.min_score drives the pre-filter only; it must not cut final AI scores."""
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    ranking_scorer = ScoreByLinkScorer({"a": 0.9, "b": 0.9})
    ai_scorer = ScoreByLinkScorer({"a": 0.8, "b": 0.1})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([]), ranking_scorer, ai_scorer
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, min_score=0.5),
        offers_to_score=10,
        offers_limit=10,
    )

    assert sorted(r.offer.link for r in results.matches) == ["a", "b"]


def test_match_offers_with_ai_use_case_sorts_by_ai_score_descending_by_default():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    ranking_scorer = ScoreByLinkScorer({"a": 0.5, "b": 0.5})
    ai_scorer = ScoreByLinkScorer({"a": 0.2, "b": 0.8})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([]), ranking_scorer, ai_scorer
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10
    )

    assert [r.offer.link for r in results.matches] == ["b", "a"]


def test_match_offers_with_ai_use_case_respects_offers_limit():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    ranking_scorer = ScoreByLinkScorer({"a": 0.5, "b": 0.5})
    ai_scorer = ScoreByLinkScorer({"a": 0.2, "b": 0.8})
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers), FilterChain([]), ranking_scorer, ai_scorer
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=1
    )

    assert len(results.matches) == 1
    assert results.matches[0].offer.link == "b"


def test_calculate_net_salary_use_case_delegates_to_the_domain_calculator():
    use_case = CalculateNetSalaryUseCase(SalaryCalculator())

    breakdown = use_case.execute(ContractType.EMPLOYMENT, 10000.0)

    assert breakdown == SalaryCalculator().calculate(ContractType.EMPLOYMENT, 10000.0)


def test_calculate_net_salary_use_case_forwards_optional_parameters():
    use_case = CalculateNetSalaryUseCase(SalaryCalculator())

    breakdown = use_case.execute(
        ContractType.B2B, 10000.0, business_costs=500.0, include_voluntary_sickness=True
    )

    assert breakdown == SalaryCalculator().calculate(
        ContractType.B2B, 10000.0, business_costs=500.0, include_voluntary_sickness=True
    )


def test_count_offers_use_case_returns_total_offers_in_repository():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
    ]
    use_case = CountOffersUseCase(FakeOfferRepository(offers))

    assert use_case.execute() == 2


def test_count_offers_use_case_returns_zero_when_repository_is_empty():
    use_case = CountOffersUseCase(FakeOfferRepository([]))

    assert use_case.execute() == 0


def test_list_offers_use_case_returns_requested_page():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
        Offer(link="c", title="C", company="C", tech_stack=["Go"]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(limit=2, offset=1, filters=OfferBrowseFilters())

    assert [offer.link for offer in results] == ["b", "c"]
    assert total == 3


def test_list_offers_use_case_returns_empty_list_past_the_end():
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(limit=10, offset=5, filters=OfferBrowseFilters())

    assert results == []
    assert total == 1


def test_list_offers_use_case_filters_by_location():
    offers = [
        Offer(link="a", title="A", company="C", locations=["Warsaw"]),
        Offer(link="b", title="B", company="C", locations=["Berlin"]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(
        limit=10, offset=0, filters=OfferBrowseFilters(location="warsaw")
    )

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_filters_by_minimum_salary():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(20000, 25000)]),
        Offer(link="b", title="B", company="C", salaries=[_salary(5000, 6000)]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(
        limit=10, offset=0, filters=OfferBrowseFilters(min_salary=20000)
    )

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_excludes_expired_offers_by_default():
    offers = [
        Offer(link="a", title="A", company="C", expired=False),
        Offer(link="b", title="B", company="C", expired=True),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(limit=10, offset=0, filters=OfferBrowseFilters())

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_includes_expired_offers_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", expired=False),
        Offer(link="b", title="B", company="C", expired=True),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(
        limit=10, offset=0, filters=OfferBrowseFilters(include_expired=True)
    )

    assert [offer.link for offer in results] == ["a", "b"]
    assert total == 2


def test_list_offers_use_case_filters_by_tech():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(limit=10, offset=0, filters=OfferBrowseFilters(tech=["python"]))

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_filters_by_search_text():
    offers = [
        Offer(link="a", title="Backend Engineer", company="Acme"),
        Offer(link="b", title="Frontend Engineer", company="Acme"),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(
        limit=10, offset=0, filters=OfferBrowseFilters(search="backend")
    )

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_combines_filters():
    offers = [
        Offer(
            link="a",
            title="Backend Engineer",
            company="Acme",
            locations=["Warsaw"],
            tech_stack=["Python"],
        ),
        Offer(
            link="b",
            title="Backend Engineer",
            company="Acme",
            locations=["Berlin"],
            tech_stack=["Python"],
        ),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(
        limit=10,
        offset=0,
        filters=OfferBrowseFilters(location="warsaw", tech=["python"], search="backend"),
    )

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_filters_by_level():
    offers = [
        Offer(link="a", title="A", company="C", levels=["Mid"]),
        Offer(link="b", title="B", company="C", levels=["Senior"]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(limit=10, offset=0, filters=OfferBrowseFilters(level=["mid"]))

    assert [offer.link for offer in results] == ["a"]
    assert total == 1


def test_list_offers_use_case_sorts_by_salary_descending_by_default():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(5000, 6000)]),
        Offer(link="b", title="B", company="C", salaries=[_salary(20000, 25000)]),
        Offer(link="c", title="C", company="C", salaries=[_salary(10000, 12000)]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, _ = use_case.execute(limit=10, offset=0, filters=OfferBrowseFilters(sort_by="salary_mid"))

    assert [offer.link for offer in results] == ["b", "c", "a"]


def test_list_offers_use_case_sorts_by_salary_ascending_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(5000, 6000)]),
        Offer(link="b", title="B", company="C", salaries=[_salary(20000, 25000)]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, _ = use_case.execute(
        limit=10, offset=0, filters=OfferBrowseFilters(sort_by="salary_mid", sort_order="asc")
    )

    assert [offer.link for offer in results] == ["a", "b"]


def test_list_offers_use_case_sorts_offers_missing_salary_last():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[]),
        Offer(link="b", title="B", company="C", salaries=[_salary(20000, 25000)]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, _ = use_case.execute(limit=10, offset=0, filters=OfferBrowseFilters(sort_by="salary_mid"))

    assert [offer.link for offer in results] == ["b", "a"]


def test_list_offers_use_case_sorts_by_recent_descending_by_default():
    offers = [
        Offer(link="a", title="A", company="C", published="2026-05-01"),
        Offer(link="b", title="B", company="C", published="2026-06-10"),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, _ = use_case.execute(limit=10, offset=0, filters=OfferBrowseFilters(sort_by="recent"))

    assert [offer.link for offer in results] == ["b", "a"]


def test_list_offers_use_case_sorts_by_recent_ascending_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", published="2026-05-01"),
        Offer(link="b", title="B", company="C", published="2026-06-10"),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, _ = use_case.execute(
        limit=10, offset=0, filters=OfferBrowseFilters(sort_by="recent", sort_order="asc")
    )

    assert [offer.link for offer in results] == ["a", "b"]


def test_list_offers_use_case_total_reflects_filtered_count_not_repository_size():
    offers = [
        Offer(link="a", title="A", company="C", locations=["Warsaw"]),
        Offer(link="b", title="B", company="C", locations=["Warsaw"]),
        Offer(link="c", title="C", company="C", locations=["Berlin"]),
    ]
    use_case = ListOffersUseCase(FakeOfferRepository(offers))

    results, total = use_case.execute(
        limit=1, offset=0, filters=OfferBrowseFilters(location="warsaw")
    )

    assert len(results) == 1
    assert total == 2


def test_match_offers_use_case_filters_by_minimum_salary():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], salaries=[_salary(20000, 25000)]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], salaries=[_salary(5000, 6000)]),
    ]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter(), SalaryFilter()])
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, min_salary=20000), offers_limit=10
    )

    assert [r.offer.link for r in results] == ["a"]


def test_match_offers_use_case_excludes_expired_offers_by_default():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], expired=False),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], expired=True),
    ]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter(), ExpiredFilter()])
    )

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=10)

    assert [r.offer.link for r in results] == ["a"]


def test_match_offers_use_case_filters_by_level():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], levels=["Mid"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], levels=["Senior"]),
    ]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter(), LevelFilter()])
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, level=["mid"]), offers_limit=10
    )

    assert [r.offer.link for r in results] == ["a"]


def test_match_offers_use_case_sorts_by_score_descending_by_default():
    candidate = _profile("Python", "FastAPI", "Docker")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python", "Java"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python", "FastAPI", "Docker"]),
    ]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=10)

    assert [r.offer.link for r in results] == ["b", "a"]


def test_match_offers_use_case_sorts_by_salary_when_requested():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], salaries=[_salary(5000, 6000)]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], salaries=[_salary(20000, 25000)]),
    ]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_limit=10, sort_by="salary_mid"
    )

    assert [r.offer.link for r in results] == ["b", "a"]


def test_match_offers_use_case_sorts_by_recent_when_requested():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], published="2026-05-01"),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], published="2026-06-10"),
    ]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter()]))

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_limit=10, sort_by="recent", sort_order="asc"
    )

    assert [r.offer.link for r in results] == ["a", "b"]


class ConcurrencyProbeScorer(OfferScorer):
    """Async scorer that records how many scoring calls overlap, so tests can assert
    the use case fans out concurrently (and respects the concurrency cap)."""

    def __init__(self, value: float = 0.5, delay: float = 0.02) -> None:
        self._value = value
        self._delay = delay
        self.in_flight = 0
        self.max_in_flight = 0

    async def score_async(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(self._delay)
        self.in_flight -= 1
        return MatchScore().with_component(ScoreComponent(name="fixed", value=self._value, weight=1.0))

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:  # pragma: no cover
        raise NotImplementedError


class FlakyScorer(OfferScorer):
    """Async scorer that fails for a set of offer links and scores the rest."""

    def __init__(self, fail_links: set[str], value: float = 0.5) -> None:
        self._fail_links = fail_links
        self._value = value

    async def score_async(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        if offer.link in self._fail_links:
            raise AiScoringError(f"scoring failed for {offer.link}")
        return MatchScore().with_component(ScoreComponent(name="fixed", value=self._value, weight=1.0))

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:  # pragma: no cover
        raise NotImplementedError


def _offers(*links: str) -> list[Offer]:
    return [Offer(link=link, title=link, company="C", tech_stack=["Python"]) for link in links]


def test_match_offers_with_ai_caps_concurrent_scoring_at_max_concurrency():
    candidate = _profile("Python")
    offers = _offers("a", "b", "c", "d", "e", "f")
    probe = ConcurrencyProbeScorer()
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({o.link: 0.5 for o in offers}),
        probe,
        max_concurrency=3,
    )

    result = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=6, offers_limit=10
    )

    assert len(result.matches) == 6
    assert probe.max_in_flight == 3


def test_match_offers_with_ai_scores_all_in_parallel_when_concurrency_is_high():
    candidate = _profile("Python")
    offers = _offers("a", "b", "c", "d", "e")
    probe = ConcurrencyProbeScorer()
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({o.link: 0.5 for o in offers}),
        probe,
        max_concurrency=10,
    )

    use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=5, offers_limit=10)

    assert probe.max_in_flight == 5


def test_match_offers_with_ai_skips_offers_that_fail_to_score():
    candidate = _profile("Python")
    offers = _offers("a", "b", "c")
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9, "b": 0.9, "c": 0.9}),
        FlakyScorer(fail_links={"b"}),
        max_concurrency=10,
    )

    result = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=3, offers_limit=10
    )

    assert sorted(m.offer.link for m in result.matches) == ["a", "c"]


def test_match_offers_with_ai_raises_when_every_offer_fails_to_score():
    candidate = _profile("Python")
    offers = _offers("a", "b")
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9, "b": 0.9}),
        FlakyScorer(fail_links={"a", "b"}),
        max_concurrency=10,
    )

    with pytest.raises(AiScoringError):
        use_case.execute(
            criteria=MatchCriteria(candidate=candidate), offers_to_score=2, offers_limit=10
        )


def test_match_offers_with_ai_use_case_returns_usage_recorded_during_scoring():
    class UsageRecordingScorer(OfferScorer):
        def __init__(self, score: float, tracker: InMemoryModelUsageTracker) -> None:
            self._score = score
            self._tracker = tracker

        def score(self, candidate, offer) -> MatchScore:
            self._tracker.record(ModelUsage(label="scoring", input_tokens=100, output_tokens=50))
            return MatchScore().with_component(ScoreComponent(name="fixed", value=self._score, weight=1.0))

    tracker = InMemoryModelUsageTracker()
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9}),
        UsageRecordingScorer(0.8, tracker),
        usage_tracker=tracker,
    )

    result = use_case.execute(
        criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10
    )

    assert len(result.usage) == 1
    assert result.usage[0].label == "scoring"
    assert result.usage[0].input_tokens == 100
    assert result.usage[0].output_tokens == 50


def test_match_offers_use_case_includes_expired_offers_when_requested():
    candidate = _profile("Python")
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], expired=False),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], expired=True),
    ]
    use_case = MatchOffersUseCase(
        FakeOfferRepository(offers), SkillBasedScorer(), FilterChain([SkillFilter(), ExpiredFilter()])
    )

    results = use_case.execute(
        criteria=MatchCriteria(candidate=candidate, include_expired=True), offers_limit=10
    )

    assert {r.offer.link for r in results} == {"a", "b"}


# --- GetModelUsageSummaryUseCase ---


def test_get_model_usage_summary_returns_summaries_with_known_limits():
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
    from app.infrastructure.no_external_usage_provider import NoExternalUsageProvider

    repo = FakeModelUsageRepository([
        ModelUsageSummary(company="Google", model="gemini-2.0-flash", input_tokens=1000, output_tokens=200),
    ])
    use_case = GetModelUsageSummaryUseCase(repo, HardcodedModelLimitsRegistry(), NoExternalUsageProvider())

    result = use_case.execute()

    assert len(result) == 1
    item = result[0]
    assert item.company == "Google"
    assert item.model == "gemini-2.0-flash"
    assert item.input_tokens == 1000
    assert item.output_tokens == 200
    assert item.limits is not None
    assert item.limits.rpm == 15
    assert item.limits.tpm == 1_000_000
    assert item.limits.rpd == 1500


def test_get_model_usage_summary_limits_are_none_for_unknown_model():
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
    from app.infrastructure.no_external_usage_provider import NoExternalUsageProvider

    repo = FakeModelUsageRepository([
        ModelUsageSummary(company="OpenAI", model="gpt-99-turbo", input_tokens=500, output_tokens=100),
    ])
    use_case = GetModelUsageSummaryUseCase(repo, HardcodedModelLimitsRegistry(), NoExternalUsageProvider())

    result = use_case.execute()

    assert result[0].limits is None


def test_get_model_usage_summary_returns_empty_when_no_usage():
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
    from app.infrastructure.no_external_usage_provider import NoExternalUsageProvider

    use_case = GetModelUsageSummaryUseCase(FakeModelUsageRepository(), HardcodedModelLimitsRegistry(), NoExternalUsageProvider())

    assert use_case.execute() == []


class FakeExternalUsageProvider(ExternalUsageProvider):
    def __init__(self, summaries: list[ModelUsageSummary]) -> None:
        self._summaries = summaries

    def get_today_usage(self) -> list[ModelUsageSummary]:
        return self._summaries


def test_use_case_prefers_external_provider_over_db_when_it_returns_data():
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry

    db_summaries = [ModelUsageSummary(company="OpenAI", model="gpt-4o", input_tokens=100, output_tokens=50)]
    external_summaries = [ModelUsageSummary(company="OpenAI", model="gpt-4o", input_tokens=9000, output_tokens=3000)]

    use_case = GetModelUsageSummaryUseCase(
        FakeModelUsageRepository(db_summaries),
        HardcodedModelLimitsRegistry(),
        FakeExternalUsageProvider(external_summaries),
    )

    result = use_case.execute()

    assert result[0].input_tokens == 9000
    assert result[0].output_tokens == 3000


def test_use_case_falls_back_to_db_when_external_provider_returns_empty():
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry

    db_summaries = [ModelUsageSummary(company="Google", model="gemini-2.0-flash", input_tokens=500, output_tokens=100)]

    use_case = GetModelUsageSummaryUseCase(
        FakeModelUsageRepository(db_summaries),
        HardcodedModelLimitsRegistry(),
        FakeExternalUsageProvider([]),
    )

    result = use_case.execute()

    assert result[0].input_tokens == 500


# --- Budget guard in MatchOffersWithAiUseCase ---


class FakeBudget(BudgetStatusReader):
    def __init__(self, limit_usd: float, used_usd: float | None) -> None:
        self._status = BudgetStatus(
            limit_usd=limit_usd,
            used_usd=used_usd,
            tracking_since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def status(self) -> BudgetStatus:
        return self._status


def _ai_use_case_with_budget(offers, budget):
    return MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9}),
        ScoreByLinkScorer({"a": 0.8}),
        budget=budget,
    )


def test_match_offers_with_ai_raises_budget_exceeded_when_usage_at_limit():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = _ai_use_case_with_budget(offers, FakeBudget(limit_usd=5.0, used_usd=5.0))

    with pytest.raises(BudgetExceededError):
        use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)


def test_match_offers_with_ai_raises_budget_exceeded_when_usage_exceeds_limit():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = _ai_use_case_with_budget(offers, FakeBudget(limit_usd=5.0, used_usd=5.50))

    with pytest.raises(BudgetExceededError) as exc_info:
        use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)

    assert exc_info.value.cost_usd == 5.50
    assert exc_info.value.limit_usd == 5.0


def test_match_offers_with_ai_proceeds_when_usage_below_limit():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = _ai_use_case_with_budget(offers, FakeBudget(limit_usd=5.0, used_usd=4.99))

    result = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)

    assert len(result.matches) == 1


def test_match_offers_with_ai_proceeds_when_usage_is_unknown():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = _ai_use_case_with_budget(offers, FakeBudget(limit_usd=5.0, used_usd=None))

    result = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)

    assert len(result.matches) == 1


def test_match_offers_with_ai_fail_closed_blocks_when_usage_is_unknown():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9}),
        ScoreByLinkScorer({"a": 0.8}),
        budget=FakeBudget(limit_usd=5.0, used_usd=None),
        fail_closed=True,
    )

    with pytest.raises(AiScoringError):
        use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)


def test_match_offers_with_ai_fail_closed_proceeds_when_usage_is_known():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9}),
        ScoreByLinkScorer({"a": 0.8}),
        budget=FakeBudget(limit_usd=5.0, used_usd=1.0),
        fail_closed=True,
    )

    result = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)

    assert len(result.matches) == 1


class InsightScorer(OfferScorer):
    """Scores every offer the same and attaches a fixed AI insight via metadata."""

    def __init__(self, insight: AiInsight, value: float = 0.8) -> None:
        self._insight = insight
        self._value = value

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        return MatchScore().with_component(
            ScoreComponent(name="description", value=self._value, weight=1.0, metadata={"ai_insight": self._insight})
        )


def test_match_offers_with_ai_attaches_ai_insight_from_the_scorer():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    insight = AiInsight(rate=5, pros=["Strong match"], cons=["Remote only"], rate_reason="Great fit")
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9}),
        InsightScorer(insight),
    )

    result = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)

    assert result.matches[0].ai_insight == insight


def test_match_offers_without_ai_leaves_ai_insight_unset():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = MatchOffersUseCase(FakeOfferRepository(offers), ScoreByLinkScorer({"a": 0.9}), FilterChain([]))

    result = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_limit=10)

    assert result[0].ai_insight is None


def test_match_offers_with_ai_proceeds_without_budget_check_when_no_cost_provider():
    candidate = _profile("Python")
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    use_case = MatchOffersWithAiUseCase(
        FakeOfferRepository(offers),
        FilterChain([]),
        ScoreByLinkScorer({"a": 0.9}),
        ScoreByLinkScorer({"a": 0.8}),
    )

    result = use_case.execute(criteria=MatchCriteria(candidate=candidate), offers_to_score=10, offers_limit=10)

    assert len(result.matches) == 1


def test_use_case_uses_db_when_no_useful_external_data():
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
    from app.infrastructure.no_external_usage_provider import NoExternalUsageProvider

    db_summaries = [ModelUsageSummary(company="Google", model="gemini-2.0-flash", input_tokens=200, output_tokens=80)]

    use_case = GetModelUsageSummaryUseCase(
        FakeModelUsageRepository(db_summaries),
        HardcodedModelLimitsRegistry(),
        NoExternalUsageProvider(),
    )

    result = use_case.execute()

    assert result[0].input_tokens == 200
