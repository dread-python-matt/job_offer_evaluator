import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.use_cases import (
    GetUserProfileUseCase,
    MatchOffersUseCase,
    SaveUserProfileUseCase,
)
from app.domain.entities import Offer, Skill, UserProfile
from app.infrastructure.scoring_strategies import SkillOverlapScoringStrategy
from app.presentation.api.routes import (
    get_match_offers_use_case,
    get_profile_use_case,
    get_save_profile_use_case,
    router,
)
from tests.unit.application.test_use_cases import (
    FakeOfferRepository,
    FakeUserProfileRepository,
)


def _build_client(profile: UserProfile | None = None, offers: list[Offer] | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    profile_repository = FakeUserProfileRepository(profile)
    offer_repository = FakeOfferRepository(offers or [])

    app.dependency_overrides[get_save_profile_use_case] = lambda: SaveUserProfileUseCase(
        profile_repository
    )
    app.dependency_overrides[get_match_offers_use_case] = lambda: MatchOffersUseCase(
        offer_repository, SkillOverlapScoringStrategy()
    )
    app.dependency_overrides[get_profile_use_case] = lambda: GetUserProfileUseCase(
        profile_repository
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
    assert body[0]["score"] == pytest.approx(0.8)


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
