from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.application.auth_use_cases import AuthenticateUserUseCase, RegisterUserUseCase
from app.domain.auth import User
from app.presentation.api.auth import (
    CookieSettings,
    get_authenticate_use_case,
    get_cookie_settings,
    get_current_user,
    get_register_use_case,
    get_token_service,
    get_user_repository,
    private_router,
    public_router,
    verify_csrf,
)
from app.presentation.api.routes import router
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository

_PASSWORD = "correct horse battery"


def _build_app() -> tuple[FastAPI, FakeUserRepository]:
    """Mirror main.py's wiring: public router unguarded, everything else behind the
    auth + CSRF guard, with in-memory fakes shared across the overrides."""
    users = FakeUserRepository()
    hasher = FakePasswordHasher()
    tokens = FakeTokenService()
    ids = iter(f"user-{i}" for i in range(1, 1000))

    app = FastAPI()
    guard = [Depends(get_current_user), Depends(verify_csrf)]
    app.include_router(public_router)
    app.include_router(private_router, dependencies=guard)
    app.include_router(router, dependencies=guard)
    app.dependency_overrides[get_register_use_case] = lambda: RegisterUserUseCase(
        users, hasher, id_factory=lambda: next(ids)
    )
    app.dependency_overrides[get_authenticate_use_case] = lambda: AuthenticateUserUseCase(
        users, hasher, tokens
    )
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_token_service] = lambda: tokens
    app.dependency_overrides[get_cookie_settings] = lambda: CookieSettings()
    return app, users


def _register(client: TestClient, email: str = "dev@example.com", password: str = _PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


# --- registration ---


def test_register_returns_201_and_sets_session_cookies():
    client = TestClient(_build_app()[0])

    response = _register(client)

    assert response.status_code == 201
    assert response.json()["email"] == "dev@example.com"
    assert client.cookies.get("access_token")
    assert client.cookies.get("csrf_token")


def test_register_rejects_duplicate_email():
    client = TestClient(_build_app()[0])
    _register(client)

    response = _register(client)

    assert response.status_code == 409


def test_register_rejects_too_short_password():
    client = TestClient(_build_app()[0])

    response = client.post("/auth/register", json={"email": "dev@example.com", "password": "short"})

    assert response.status_code == 422


def test_register_rejects_invalid_email():
    client = TestClient(_build_app()[0])

    response = client.post("/auth/register", json={"email": "not-an-email", "password": _PASSWORD})

    assert response.status_code == 422


# --- login ---


def test_login_with_valid_credentials_sets_cookies():
    client = TestClient(_build_app()[0])
    _register(client)
    client.cookies.clear()

    response = client.post("/auth/login", json={"email": "dev@example.com", "password": _PASSWORD})

    assert response.status_code == 200
    assert client.cookies.get("access_token")


def test_login_with_wrong_password_is_unauthorized():
    client = TestClient(_build_app()[0])
    _register(client)
    client.cookies.clear()

    response = client.post(
        "/auth/login", json={"email": "dev@example.com", "password": "wrong wrong wrong"}
    )

    assert response.status_code == 401


# --- the guard ---


def test_me_requires_authentication():
    client = TestClient(_build_app()[0])

    assert client.get("/auth/me").status_code == 401


def test_me_returns_current_user_when_authenticated():
    client = TestClient(_build_app()[0])
    _register(client)

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "dev@example.com"


def test_app_routes_are_guarded():
    client = TestClient(_build_app()[0])

    # A protected app route returns 401 (guard runs before the route's use case).
    assert client.get("/offers/count").status_code == 401


def test_stale_token_version_is_rejected():
    app, users = _build_app()
    client = TestClient(app)
    _register(client)
    stored = users.get_by_email("dev@example.com")
    # Simulate a logout-everywhere / password change: bump the user's token_version so
    # the already-issued cookie (version 0) no longer matches.
    users.add(
        User(
            id=stored.id,
            email=stored.email,
            password_hash=stored.password_hash,
            token_version=stored.token_version + 1,
            created_at=stored.created_at,
        )
    )

    assert client.get("/auth/me").status_code == 401


# --- CSRF ---


def test_mutating_request_without_csrf_header_is_forbidden():
    client = TestClient(_build_app()[0])
    _register(client)

    # Authenticated (cookie present) but no X-CSRF-Token header.
    assert client.post("/auth/logout").status_code == 403


def test_mutating_request_with_matching_csrf_header_succeeds():
    client = TestClient(_build_app()[0])
    _register(client)
    csrf = client.cookies.get("csrf_token")

    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})

    assert response.status_code == 204
