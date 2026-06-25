import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datetime import datetime, timezone

from app.application.ai_scoring_context import AiScoringContext
from app.application.budget_service import BudgetService
from app.application.ports import AvailableModel, ModelUsageSummary
from app.application.use_cases import (
    CalculateNetSalaryUseCase,
    CountOffersUseCase,
    GetModelUsageSummaryUseCase,
    GetUserProfileUseCase,
    ListAvailableModelsUseCase,
    ListOffersUseCase,
    MatchOffersUseCase,
    MatchOffersWithAiUseCase,
    SaveUserProfileUseCase,
)
from app.domain.budget import BudgetSettings
from app.domain.errors import AiScoringError
from app.domain.entities import Offer, Salary, Skill, UserProfile
from app.domain.filters import FilterChain
from app.domain.auth import User
from app.domain.scoring import AiInsight, MatchScore, OfferScorer, ScoreComponent
from app.domain.salary_calculator import ContractType, SalaryCalculator
from app.infrastructure.offer_filters import (
    ExpiredFilter,
    LevelFilter,
    LocationFilter,
    SalaryFilter,
    SkillFilter,
)
from app.infrastructure.scoring_strategies import SkillBasedScorer
from app.domain.errors import BudgetExceededError
from app.presentation.api.auth import get_current_user
from app.presentation.api.routes import (
    get_ai_scoring_context,
    get_budget_service,
    get_calculate_salary_use_case,
    get_count_offers_use_case,
    get_list_available_models_use_case,
    get_list_offers_use_case,
    get_match_offers_ai_use_case,
    get_match_offers_use_case,
    get_model_usage_summary_use_case,
    get_profile_use_case,
    get_save_profile_use_case,
    router,
)
from tests.fakes import (
    FakeModelUsageRepository,
    FakeOfferRepository,
    FakeUserProfileRepository,
    FixedUserSpendProvider,
    InMemoryBudgetRepository,
    InMemorySelectedModelRepository,
    ScoreByLinkScorer,
)


def test_health_returns_ok_without_dependencies():
    from app.presentation.api.auth import public_router

    app = FastAPI()
    app.include_router(public_router)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _salary(
    min_amount: float, max_amount: float, period: str = "month", contract_type: str = "permanent"
) -> Salary:
    # Net figures drive filtering/sorting/display now; stand in with the gross numbers.
    return Salary(
        contract_type=contract_type,
        min_amount=min_amount,
        max_amount=max_amount,
        currency="PLN",
        period=period,
        net_min=min_amount,
        net_mid=(min_amount + max_amount) / 2,
        net_max=max_amount,
    )


def _build_client(
    profile: UserProfile | None = None,
    offers: list[Offer] | None = None,
    ai_scorer: OfferScorer | None = None,
    usage_summaries: list[ModelUsageSummary] | None = None,
) -> TestClient:
    from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry

    app = FastAPI()
    app.include_router(router)

    # Routes resolve the caller via get_current_user; tests run with a fixed fake user.
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user-1", email="dev@example.com", password_hash="x"
    )

    profile_repository = FakeUserProfileRepository(profile)
    offer_repository = FakeOfferRepository(offers or [])
    filter_chain = FilterChain(
        [SkillFilter(), LocationFilter(), SalaryFilter(), ExpiredFilter(), LevelFilter()]
    )

    app.dependency_overrides[get_save_profile_use_case] = lambda: SaveUserProfileUseCase(
        profile_repository
    )
    app.dependency_overrides[get_match_offers_use_case] = lambda: MatchOffersUseCase(
        offer_repository, SkillBasedScorer(), filter_chain
    )
    app.dependency_overrides[get_match_offers_ai_use_case] = lambda: MatchOffersWithAiUseCase(
        offer_repository, filter_chain, SkillBasedScorer(), ai_scorer or SkillBasedScorer()
    )
    app.dependency_overrides[get_profile_use_case] = lambda: GetUserProfileUseCase(
        profile_repository
    )
    app.dependency_overrides[get_count_offers_use_case] = lambda: CountOffersUseCase(
        offer_repository
    )
    app.dependency_overrides[get_list_offers_use_case] = lambda: ListOffersUseCase(
        offer_repository
    )
    app.dependency_overrides[get_calculate_salary_use_case] = lambda: CalculateNetSalaryUseCase(SalaryCalculator())
    app.dependency_overrides[get_model_usage_summary_use_case] = lambda: GetModelUsageSummaryUseCase(
        FakeModelUsageRepository(usage_summaries or []), HardcodedModelLimitsRegistry()
    )
    return TestClient(app)


def _profile_payload() -> dict:
    return {
        "summary": "Backend developer",
        "skills": [{"name": "Python", "rating": 5}],
        "projects": [
            {
                "name": "Evaluator",
                "repository_link": "https://github.com/user/evaluator",
                "summary": "Job matching app",
                "date_from": "2026-01",
                "date_to": "2026-06",
                "tech_stack": ["Python", "FastAPI"],
            }
        ],
        "experience": [
            {
                "title": "Backend Developer",
                "company": "Acme",
                "description": "Built APIs",
                "date_from": "2024-01",
                "date_to": "2025-12",
                "tech_stack": ["Python"],
            }
        ],
    }


def test_post_profile_saves_and_returns_profile():
    client = _build_client()

    response = client.post("/profile", json=_profile_payload())

    assert response.status_code == 200
    assert response.json()["summary"] == "Backend developer"
    assert response.json()["skills"] == [{"name": "Python", "rating": 5}]


def test_profile_round_trips_optional_tax_situation():
    client = _build_client(profile=None)
    payload = {
        **_profile_payload(),
        "tax_situation": {"under_26": True, "is_student": True, "applies_tax_credit": False},
    }

    assert client.post("/profile", json=payload).status_code == 200
    assert client.get("/profile").json()["tax_situation"] == {
        "under_26": True,
        "is_student": True,
        "applies_tax_credit": False,
        "b2b_tax_form": "ryczalt_12",
        "b2b_zus_scheme": "duzy_zus",
    }


def test_profile_defaults_tax_situation_when_omitted():
    client = _build_client()

    response = client.post("/profile", json=_profile_payload())

    assert response.status_code == 200
    assert response.json()["tax_situation"] == {
        "under_26": False,
        "is_student": False,
        "applies_tax_credit": True,
        "b2b_tax_form": "ryczalt_12",
        "b2b_zus_scheme": "duzy_zus",
    }


def test_profile_round_trips_b2b_tax_settings():
    client = _build_client(profile=None)
    payload = {
        **_profile_payload(),
        "tax_situation": {"b2b_tax_form": "liniowy", "b2b_zus_scheme": "preferential"},
    }

    assert client.post("/profile", json=payload).status_code == 200
    body = client.get("/profile").json()["tax_situation"]
    assert body["b2b_tax_form"] == "liniowy"
    assert body["b2b_zus_scheme"] == "preferential"


def test_get_profile_returns_404_when_no_profile_saved():
    client = _build_client(profile=None)

    response = client.get("/profile")

    assert response.status_code == 404


def test_get_profile_returns_saved_profile():
    profile = UserProfile(
        summary="Backend developer",
        skills=[Skill(name="Python", rating=5)],
        projects=[],
        experience=[],
    )
    client = _build_client(profile=profile)

    response = client.get("/profile")

    assert response.status_code == 200
    assert response.json()["summary"] == "Backend developer"


def test_match_offers_returns_offers_sorted_by_score():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python", "Java"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python", "FastAPI"]),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [
                    {"name": "Python", "rating": 5},
                    {"name": "FastAPI", "rating": 4},
                ],
                "projects": [],
                "experience": [],
            },
            "offers_limit": 10,
            "min_score": 0.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body] == ["b", "a"]
    assert body[0]["score"] == pytest.approx(0.9)


def test_match_offers_returns_all_matches_when_offers_limit_is_omitted():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["a", "b"]


def test_get_offers_count_returns_total_offers():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers/count")

    assert response.status_code == 200
    assert response.json() == {"total": 2}


def test_list_offers_returns_default_page():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers")

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a", "b"]
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_list_offers_respects_limit_and_offset():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
        Offer(link="c", title="C", company="C", tech_stack=["Go"]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["b"]
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_list_offers_filters_by_location():
    offers = [
        Offer(link="a", title="A", company="C", locations=["Warsaw"]),
        Offer(link="b", title="B", company="C", locations=["Berlin"]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"location": "warsaw"})

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a"]
    assert body["total"] == 1


def test_list_offers_filters_by_minimum_salary():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(20000, 25000)]),
        Offer(link="b", title="B", company="C", salaries=[_salary(5000, 6000)]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"min_salary": 20000})

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a"]
    assert body["total"] == 1


def test_list_offers_excludes_expired_offers_by_default():
    offers = [
        Offer(link="a", title="A", company="C", expired=False),
        Offer(link="b", title="B", company="C", expired=True),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers")

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a"]
    assert body["total"] == 1


def test_list_offers_includes_expired_offers_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", expired=False),
        Offer(link="b", title="B", company="C", expired=True),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"include_expired": True})

    assert response.status_code == 200
    body = response.json()
    assert {offer["link"] for offer in body["offers"]} == {"a", "b"}
    assert body["total"] == 2


def test_list_offers_filters_by_tech():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Java"]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"tech": "python"})

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a"]
    assert body["total"] == 1


def test_list_offers_filters_by_search_text():
    offers = [
        Offer(link="a", title="Backend Engineer", company="Acme"),
        Offer(link="b", title="Frontend Engineer", company="Acme"),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"search": "backend"})

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a"]
    assert body["total"] == 1


def test_list_offers_filters_by_level():
    offers = [
        Offer(link="a", title="A", company="C", levels=["Mid"]),
        Offer(link="b", title="B", company="C", levels=["Senior"]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"level": "mid"})

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["offers"]] == ["a"]
    assert body["total"] == 1


def test_list_offers_sorts_by_salary_descending_by_default():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(5000, 6000)]),
        Offer(link="b", title="B", company="C", salaries=[_salary(20000, 25000)]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"sort_by": "salary_mid"})

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()["offers"]] == ["b", "a"]


def test_list_offers_sorts_by_salary_ascending_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(5000, 6000)]),
        Offer(link="b", title="B", company="C", salaries=[_salary(20000, 25000)]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"sort_by": "salary_mid", "sort_order": "asc"})

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()["offers"]] == ["a", "b"]


def test_list_offers_sorts_by_recent():
    offers = [
        Offer(link="a", title="A", company="C", published="2026-05-01"),
        Offer(link="b", title="B", company="C", published="2026-06-10"),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers", params={"sort_by": "recent"})

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()["offers"]] == ["b", "a"]


def test_list_offers_exposes_published_date():
    offers = [Offer(link="a", title="A", company="C", published="2026-05-01")]
    client = _build_client(offers=offers)

    response = client.get("/offers")

    assert response.json()["offers"][0]["published"] == "2026-05-01"


def test_list_offers_exposes_estimated_net_midpoint_as_net_monthly():
    offers = [
        Offer(link="a", title="A", company="C", salaries=[_salary(10000, 12000, contract_type="b2b")]),
    ]
    client = _build_client(offers=offers)

    response = client.get("/offers")

    assert response.status_code == 200
    salary = response.json()["offers"][0]["salaries"][0]
    assert salary["net_monthly"] == 11000  # midpoint of the standardized net
    assert salary["net_min"] == 10000
    assert salary["net_max"] == 12000


def test_list_offers_exposes_null_net_when_salary_has_no_normalized_figures():
    no_net = Salary(contract_type="permanent", min_amount=10000, max_amount=12000, currency="PLN", period="month")
    offers = [Offer(link="a", title="A", company="C", salaries=[no_net])]
    client = _build_client(offers=offers)

    response = client.get("/offers")

    assert response.status_code == 200
    assert response.json()["offers"][0]["salaries"][0]["net_monthly"] is None


def test_match_offers_filters_by_level():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], levels=["Mid"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], levels=["Senior"]),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "level": ["mid"],
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["a"]


def test_match_offers_sorts_by_salary_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], salaries=[_salary(5000, 6000)]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], salaries=[_salary(20000, 25000)]),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "sort_by": "salary_mid",
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["b", "a"]


def test_match_offers_sorts_by_recent_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], published="2026-05-01"),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], published="2026-06-10"),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "sort_by": "recent",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["a", "b"]


def test_match_offers_score_recent_ranks_by_score_first():
    # "a" is more recent but requires Rust which the candidate barely knows (rating 1)
    # "b" is older but requires Python which the candidate knows well (rating 5)
    # score wins over recency → "b" should come first
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Rust"], published="2026-06-20"),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], published="2026-01-01"),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}, {"name": "Rust", "rating": 1}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "sort_by": "score_recent",
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["b", "a"]


def test_match_offers_score_recent_breaks_ties_by_recency():
    # same tech stack → equal scores, more recent published date wins
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], published="2026-05-01"),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], published="2026-06-10"),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "sort_by": "score_recent",
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["b", "a"]


def test_match_offers_filters_by_location():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], locations=["Warsaw"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], locations=["Berlin"]),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "location": "warsaw",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body] == ["a"]
    assert body[0]["locations"] == ["Warsaw"]


def test_match_offers_filters_by_minimum_salary():
    offers = [
        Offer(
            link="a", title="A", company="C", tech_stack=["Python"],
            salaries=[_salary(20000, 25000)],
        ),
        Offer(
            link="b", title="B", company="C", tech_stack=["Python"],
            salaries=[_salary(5000, 6000)],
        ),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "min_salary": 20000,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body] == ["a"]
    assert body[0]["salaries"] == [
        {
            "contract_type": "permanent",
            "min": 20000,
            "max": 25000,
            "currency": "PLN",
            "period": "month",
            "net_monthly": 22500,  # midpoint of the standardized net
            "net_min": 20000,
            "net_max": 25000,
        }
    ]


def test_match_offers_excludes_expired_offers_by_default():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], expired=False),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], expired=True),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()] == ["a"]


def test_match_offers_includes_expired_offers_when_requested():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"], expired=False),
        Offer(link="b", title="B", company="C", tech_stack=["Python"], expired=True),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "include_expired": True,
        },
    )

    assert response.status_code == 200
    assert {offer["link"] for offer in response.json()} == {"a", "b"}


def test_match_offers_filters_by_minimum_score():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python", "Java"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python", "FastAPI"]),
    ]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "offers_limit": 10,
            "min_score": 0.6,
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_match_offers_ai_filters_final_results_by_ai_min_score():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    ai_scorer = ScoreByLinkScorer({"a": 0.8, "b": 0.1})
    client = _build_client(offers=offers, ai_scorer=ai_scorer)

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "ai_min_score": 0.5,
            "offers_to_score": 10,
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()["matches"]] == ["a"]


class _InsightScorer(OfferScorer):
    def __init__(self, insight: AiInsight) -> None:
        self._insight = insight

    def score(self, candidate, offer) -> MatchScore:
        return MatchScore().with_component(
            ScoreComponent(name="description", value=0.9, weight=1.0, metadata={"ai_insight": self._insight})
        )


def test_match_offers_ai_response_includes_ai_insight():
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    insight = AiInsight(rate=4, pros=["Strong Python"], cons=["No K8s"], rate_reason="Solid fit")
    client = _build_client(offers=offers, ai_scorer=_InsightScorer(insight))

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {"summary": "", "skills": [{"name": "Python", "rating": 5}], "projects": [], "experience": []},
            "offers_to_score": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["matches"][0]["ai_insight"] == {
        "rate": 4,
        "pros": ["Strong Python"],
        "cons": ["No K8s"],
        "rate_reason": "Solid fit",
    }


def test_match_offers_response_has_null_ai_insight():
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match",
        json={
            "candidate": {"summary": "", "skills": [{"name": "Python", "rating": 5}], "projects": [], "experience": []},
            "offers_limit": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["ai_insight"] is None


def test_match_offers_ai_returns_offers_scored_by_the_ai_scorer():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python"]),
    ]
    ai_scorer = ScoreByLinkScorer({"a": 0.2, "b": 0.9})
    client = _build_client(offers=offers, ai_scorer=ai_scorer)

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "offers_to_score": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [offer["link"] for offer in body["matches"]] == ["b", "a"]
    assert body["matches"][0]["score"] == pytest.approx(0.9)


def test_match_offers_ai_only_sends_top_ranked_offers_to_the_ai_scorer():
    offers = [
        Offer(link="a", title="A", company="C", tech_stack=["Python", "FastAPI", "Docker"]),
        Offer(link="b", title="B", company="C", tech_stack=["Python", "Java"]),
        Offer(link="c", title="C", company="C", tech_stack=["Java"]),
    ]
    ai_scorer = ScoreByLinkScorer({"a": 0.5, "b": 0.5, "c": 0.5})
    client = _build_client(offers=offers, ai_scorer=ai_scorer)

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [
                    {"name": "Python", "rating": 5},
                    {"name": "FastAPI", "rating": 4},
                    {"name": "Docker", "rating": 3},
                ],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
            "offers_to_score": 1,
        },
    )

    assert response.status_code == 200
    assert sorted(ai_scorer.scored_links) == ["a"]


def test_match_offers_ai_uses_default_offers_to_score_when_omitted():
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
        },
    )

    assert response.status_code == 200
    assert [offer["link"] for offer in response.json()["matches"]] == ["a"]


def test_match_offers_ai_rejects_offers_to_score_above_the_cap():
    client = _build_client()

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {"summary": "", "skills": [], "projects": [], "experience": []},
            "offers_to_score": 51,
        },
    )

    assert response.status_code == 422


def test_match_offers_ai_rejects_offers_to_score_below_one():
    client = _build_client()

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {"summary": "", "skills": [], "projects": [], "experience": []},
            "offers_to_score": 0,
        },
    )

    assert response.status_code == 422


def test_match_offers_ai_response_includes_usage_with_token_counts():
    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    client = _build_client(offers=offers)

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "usage" in body
    assert "input_tokens" in body["usage"]
    assert "output_tokens" in body["usage"]


def test_calculate_salary_for_employment_contract():
    client = _build_client()

    response = client.post(
        "/salary/calculate", json={"contract_type": "employment", "gross_monthly": 10000.0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gross"] == pytest.approx(10000.0)
    assert body["social_security"] == pytest.approx(1371.0)
    assert body["health_insurance"] == pytest.approx(776.61, abs=0.01)
    assert body["income_tax"] == pytest.approx(705.48, abs=0.01)
    assert body["ppk"] == 0.0
    assert body["take_home"] == pytest.approx(7146.91, abs=0.01)


def test_calculate_salary_for_employment_contract_with_ppk():
    client = _build_client()

    response = client.post(
        "/salary/calculate",
        json={"contract_type": "employment", "gross_monthly": 10000.0, "include_ppk": True},
    )

    assert response.status_code == 200
    assert response.json()["ppk"] == pytest.approx(200.0)


def test_calculate_salary_for_civil_contract():
    client = _build_client()

    response = client.post(
        "/salary/calculate", json={"contract_type": "civil", "gross_monthly": 8000.0}
    )

    assert response.status_code == 200
    assert response.json()["take_home"] == pytest.approx(6078.75, abs=0.01)


def test_calculate_salary_for_b2b_contract_with_business_costs():
    client = _build_client()

    response = client.post(
        "/salary/calculate",
        json={"contract_type": "b2b", "gross_monthly": 10000.0, "business_costs": 1000.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["business_costs"] == pytest.approx(1000.0)
    assert body["take_home"] == pytest.approx(
        SalaryCalculator().calculate(ContractType.B2B, 10000.0, business_costs=1000.0).take_home,
        abs=0.01,
    )


def test_calculate_salary_rounds_money_fields_to_cents():
    client = _build_client()

    response = client.post(
        "/salary/calculate",
        json={"contract_type": "b2b", "gross_monthly": 10000.0, "business_costs": 500.0},
    )

    assert response.status_code == 200
    body = response.json()
    for field in ("gross", "social_security", "health_insurance", "income_tax", "business_costs", "ppk", "take_home"):
        value = body[field]
        assert value == round(value, 2), f"{field}={value} has sub-cent precision"


def test_calculate_salary_rejects_unknown_contract_type():
    client = _build_client()

    response = client.post(
        "/salary/calculate", json={"contract_type": "freelance", "gross_monthly": 10000.0}
    )

    assert response.status_code == 422


def test_calculate_salary_rejects_non_positive_gross_amount():
    client = _build_client()

    response = client.post(
        "/salary/calculate", json={"contract_type": "b2b", "gross_monthly": 0}
    )

    assert response.status_code == 422


def test_calculate_salary_waives_income_tax_for_under_26():
    client = _build_client()

    response = client.post(
        "/salary/calculate",
        json={"contract_type": "employment", "gross_monthly": 10000.0, "under_26": True},
    )

    assert response.status_code == 200
    assert response.json()["income_tax"] == 0.0


def test_calculate_salary_without_pit2_credit_increases_income_tax():
    client = _build_client()

    base = client.post(
        "/salary/calculate", json={"contract_type": "employment", "gross_monthly": 10000.0}
    ).json()
    without_credit = client.post(
        "/salary/calculate",
        json={
            "contract_type": "employment",
            "gross_monthly": 10000.0,
            "applies_tax_credit": False,
        },
    ).json()

    assert without_credit["income_tax"] == pytest.approx(base["income_tax"] + 300.0)


def test_calculate_salary_honours_b2b_tax_form():
    client = _build_client()

    ryczalt = client.post(
        "/salary/calculate", json={"contract_type": "b2b", "gross_monthly": 10000.0}
    ).json()
    liniowy = client.post(
        "/salary/calculate",
        json={"contract_type": "b2b", "gross_monthly": 10000.0, "b2b_tax_form": "liniowy"},
    ).json()

    assert liniowy["income_tax"] != ryczalt["income_tax"]


def test_calculate_salary_rejects_unknown_b2b_tax_form():
    client = _build_client()

    response = client.post(
        "/salary/calculate",
        json={"contract_type": "b2b", "gross_monthly": 10000.0, "b2b_tax_form": "bogus"},
    )

    assert response.status_code == 422


def test_match_offers_ai_returns_503_when_scoring_service_unavailable():
    class FailingScorer(OfferScorer):
        def score(self, candidate, offer) -> MatchScore:
            raise AiScoringError("Gemini rate limit exceeded")

    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    client = _build_client(offers=offers, ai_scorer=FailingScorer())

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
        },
    )

    assert response.status_code == 503


# --- GET /usage/summary ---


def test_usage_summary_returns_empty_list_when_no_usage():
    client = _build_client()

    response = client.get("/usage/summary")

    assert response.status_code == 200
    assert response.json() == []


def test_usage_summary_returns_model_usage_with_limits():
    client = _build_client(usage_summaries=[
        ModelUsageSummary(company="Google", model="gemini-2.0-flash", input_tokens=1000, output_tokens=200),
    ])

    response = client.get("/usage/summary")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["company"] == "Google"
    assert item["model"] == "gemini-2.0-flash"
    assert item["input_tokens"] == 1000
    assert item["output_tokens"] == 200
    assert item["limits"]["rpm"] == 15
    assert item["limits"]["tpm"] == 1_000_000
    assert item["limits"]["rpd"] == 1500


def test_usage_summary_limits_are_null_for_unknown_model():
    client = _build_client(usage_summaries=[
        ModelUsageSummary(company="OpenAI", model="gpt-unknown-99", input_tokens=500, output_tokens=100),
    ])

    response = client.get("/usage/summary")

    assert response.status_code == 200
    assert response.json()[0]["limits"] is None


# --- GET /config/models and PUT /config/model ---


class _FakeAvailableModelsProvider:
    def __init__(self, models: list[AvailableModel]) -> None:
        self._models = models

    def list_models(self) -> list[AvailableModel]:
        return self._models


def _build_model_client(
    available_models: list[AvailableModel],
    initial_model: str = "gemini-2.0-flash",
) -> tuple[TestClient, AiScoringContext]:
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_current_user] = lambda: User(
        id="user-1", email="dev@example.com", password_hash="x"
    )

    use_case = ListAvailableModelsUseCase(_FakeAvailableModelsProvider(available_models))
    context = AiScoringContext(
        repository=InMemorySelectedModelRepository(initial_model),
        build_use_case=lambda model: object(),
        configure_sdk=lambda model: None,
        default_model=initial_model,
    )

    app.dependency_overrides[get_list_available_models_use_case] = lambda: use_case
    app.dependency_overrides[get_ai_scoring_context] = lambda: context
    return TestClient(app), context


def test_get_available_models_groups_by_company():
    models = [
        AvailableModel(model="gemini-2.0-flash", company="Google"),
        AvailableModel(model="gemini-1.5-pro", company="Google"),
        AvailableModel(model="gpt-4o", company="OpenAI"),
    ]
    client, _ = _build_model_client(models)

    response = client.get("/config/models")

    assert response.status_code == 200
    body = response.json()
    companies = {c["name"]: c["models"] for c in body["companies"]}
    assert set(companies["Google"]) == {"gemini-2.0-flash", "gemini-1.5-pro"}
    assert set(companies["OpenAI"]) == {"gpt-4o"}


def test_get_available_models_includes_active_model():
    models = [AvailableModel(model="gemini-2.0-flash", company="Google")]
    client, _ = _build_model_client(models, initial_model="gemini-2.0-flash")

    response = client.get("/config/models")

    assert response.status_code == 200
    assert response.json()["active"]["model"] == "gemini-2.0-flash"
    assert response.json()["active"]["company"] == "Google"


def test_put_model_switches_active_model():
    models = [
        AvailableModel(model="gemini-2.0-flash", company="Google"),
        AvailableModel(model="gpt-4o", company="OpenAI"),
    ]
    client, context = _build_model_client(models, initial_model="gemini-2.0-flash")

    response = client.put("/config/model", json={"model": "gpt-4o"})

    assert response.status_code == 200
    assert response.json()["model"] == "gpt-4o"
    assert response.json()["company"] == "OpenAI"
    assert context.active_model_for("user-1") == "gpt-4o"


def test_put_model_returns_404_for_unknown_model():
    models = [AvailableModel(model="gemini-2.0-flash", company="Google")]
    client, _ = _build_model_client(models)

    response = client.put("/config/model", json={"model": "gpt-unknown-99"})

    assert response.status_code == 404


# --- /usage budget endpoints and budget blocking ---


_ANCHOR = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _build_budget_client(limit_usd: float = 5.0, spend_provider=None) -> tuple[TestClient, BudgetService]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user-1", email="dev@example.com", password_hash="x"
    )
    repo = InMemoryBudgetRepository(BudgetSettings(limit_usd=limit_usd, tracking_since=_ANCHOR))
    service = BudgetService(repo, spend_provider)
    app.dependency_overrides[get_budget_service] = lambda: service
    return TestClient(app), service


def test_get_usage_cost_returns_used_and_limit():
    client, _ = _build_budget_client(limit_usd=5.0, spend_provider=FixedUserSpendProvider(2.50))

    response = client.get("/usage/cost")

    assert response.status_code == 200
    assert response.json() == {"cost_usd": 2.50, "limit_usd": 5.0}


def test_get_usage_cost_returns_null_when_spend_unknown():
    client, _ = _build_budget_client(spend_provider=None)

    response = client.get("/usage/cost")

    assert response.status_code == 200
    assert response.json() is None


def test_put_usage_limit_sets_the_limit():
    client, service = _build_budget_client(limit_usd=5.0, spend_provider=FixedUserSpendProvider(1.0))

    response = client.put("/usage/limit", json={"limit_usd": 25.0})

    assert response.status_code == 200
    assert response.json()["limit_usd"] == 25.0
    assert response.json()["used_usd"] == 1.0
    assert service.status("user-1").limit_usd == 25.0


def test_put_usage_limit_rejects_negative_limit():
    client, _ = _build_budget_client()

    response = client.put("/usage/limit", json={"limit_usd": -1.0})

    assert response.status_code == 422


def test_post_usage_reset_moves_the_tracking_anchor_forward():
    client, service = _build_budget_client(spend_provider=FixedUserSpendProvider(0.0))

    response = client.post("/usage/reset")

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["tracking_since"]) > _ANCHOR


def test_match_offers_ai_returns_402_when_budget_exceeded():
    class BudgetExceededScorer(OfferScorer):
        def score(self, candidate, offer) -> MatchScore:
            raise BudgetExceededError(5.0, 5.0)

    offers = [Offer(link="a", title="A", company="C", tech_stack=["Python"])]
    client = _build_client(offers=offers, ai_scorer=BudgetExceededScorer())

    response = client.post(
        "/offers/match/ai",
        json={
            "candidate": {
                "summary": "",
                "skills": [{"name": "Python", "rating": 5}],
                "projects": [],
                "experience": [],
            },
            "min_score": 0.0,
        },
    )

    assert response.status_code == 402
