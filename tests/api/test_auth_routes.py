from dataclasses import replace
from datetime import timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.application.auth_use_cases import (
    AuthenticateUserUseCase,
    ChangePasswordUseCase,
    RegisterUserUseCase,
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
    VerifyEmailUseCase,
)
from app.infrastructure.in_memory_rate_limiter import InMemoryRateLimiter
from app.presentation.api.auth import (
    CookieSettings,
    get_authenticate_use_case,
    get_cookie_settings,
    get_change_password_use_case,
    get_current_user,
    get_rate_limiter,
    get_register_use_case,
    get_request_password_reset_use_case,
    get_reset_password_use_case,
    get_token_service,
    get_user_repository,
    get_verify_email_use_case,
    private_router,
    public_router,
    verify_csrf,
)
from app.presentation.api.routes import router
from tests.fakes import (
    FakeEmailSender,
    FakeEmailValidator,
    FakePasswordHasher,
    FakePasswordResetTokenService,
    FakeTokenService,
    FakeUserRepository,
    FakeVerificationTokenService,
)

_PASSWORD = "correct horse battery"
_NEW_PASSWORD = "a brand new passphrase"
_VERIFY_LINK = "http://app.test/verify-email?token="
_RESET_LINK = "http://app.test/reset-password?token="
_RATE_LIMIT_ATTEMPTS = 3


class _Ctx:
    """The wired app plus the in-memory collaborators tests need to inspect (the user
    store and the captured outbound emails)."""

    def __init__(self, app: FastAPI, users: FakeUserRepository, sender: FakeEmailSender) -> None:
        self.app = app
        self.users = users
        self.sender = sender


def _build_app() -> _Ctx:
    """Mirror main.py's wiring: public router unguarded, everything else behind the
    auth + CSRF guard, with in-memory fakes shared across the overrides."""
    users = FakeUserRepository()
    hasher = FakePasswordHasher()
    tokens = FakeTokenService()
    verification_tokens = FakeVerificationTokenService()
    reset_tokens = FakePasswordResetTokenService()
    sender = FakeEmailSender()
    ids = iter(f"user-{i}" for i in range(1, 1000))

    app = FastAPI()
    guard = [Depends(get_current_user), Depends(verify_csrf)]
    app.include_router(public_router)
    app.include_router(private_router, dependencies=guard)
    app.include_router(router, dependencies=guard)
    app.dependency_overrides[get_register_use_case] = lambda: RegisterUserUseCase(
        users,
        hasher,
        email_validator=FakeEmailValidator(),
        verification_tokens=verification_tokens,
        email_sender=sender,
        link_builder=lambda token: f"{_VERIFY_LINK}{token}",
        id_factory=lambda: next(ids),
    )
    app.dependency_overrides[get_authenticate_use_case] = lambda: AuthenticateUserUseCase(
        users, hasher, tokens
    )
    app.dependency_overrides[get_verify_email_use_case] = lambda: VerifyEmailUseCase(
        users, verification_tokens, tokens
    )
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_token_service] = lambda: tokens
    app.dependency_overrides[get_cookie_settings] = lambda: CookieSettings()
    rate_limiter = InMemoryRateLimiter(
        max_attempts=_RATE_LIMIT_ATTEMPTS, window=timedelta(minutes=15)
    )
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    app.dependency_overrides[get_change_password_use_case] = lambda: ChangePasswordUseCase(
        users, hasher, tokens
    )
    app.dependency_overrides[get_request_password_reset_use_case] = lambda: (
        RequestPasswordResetUseCase(
            users,
            reset_tokens,
            sender,
            link_builder=lambda token: f"{_RESET_LINK}{token}",
        )
    )
    app.dependency_overrides[get_reset_password_use_case] = lambda: ResetPasswordUseCase(
        users, reset_tokens, hasher, tokens
    )
    return _Ctx(app, users, sender)


def _register(
    client: TestClient,
    email: str = "dev@example.com",
    password: str = _PASSWORD,
    confirm_password: str | None = None,
):
    return client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            # Default to a matching retype so callers only set it when testing a mismatch.
            "confirm_password": password if confirm_password is None else confirm_password,
        },
    )


def _token_from_email(body: str) -> str:
    """Pull the confirmation token out of the link embedded in a sent email."""
    return body.split("token=", 1)[1].split()[0]


def _verify_latest(client: TestClient, sender: FakeEmailSender):
    token = _token_from_email(sender.sent[-1]["body"])
    return client.post("/auth/verify-email", json={"token": token})


def _register_and_verify(
    client: TestClient, sender: FakeEmailSender, email: str = "dev@example.com"
):
    """Run the full happy path so the client ends up authenticated (verify issues the
    session cookies), the way the old auto-login register used to leave it."""
    _register(client, email=email)
    return _verify_latest(client, sender)


# --- registration ---


def test_register_returns_202_and_does_not_set_session_cookies():
    ctx = _build_app()
    client = TestClient(ctx.app)

    response = _register(client)

    assert response.status_code == 202
    assert response.json()["email"] == "dev@example.com"
    # Registration no longer logs the user in; confirmation does.
    assert client.cookies.get("access_token") is None
    assert client.cookies.get("csrf_token") is None


def test_register_sends_a_confirmation_email_with_a_link():
    ctx = _build_app()
    client = TestClient(ctx.app)

    _register(client)

    assert len(ctx.sender.sent) == 1
    assert ctx.sender.sent[0]["to"] == "dev@example.com"
    assert "token=" in ctx.sender.sent[0]["body"]


def test_register_creates_an_unverified_account():
    ctx = _build_app()
    client = TestClient(ctx.app)

    _register(client)

    assert ctx.users.get_by_email("dev@example.com").email_verified is False


def test_register_rejects_duplicate_email():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register(client)

    response = _register(client)

    assert response.status_code == 409


def test_register_rejects_too_short_password():
    client = TestClient(_build_app().app)

    response = _register(client, password="short")

    assert response.status_code == 422


def test_register_rejects_invalid_email():
    client = TestClient(_build_app().app)

    response = _register(client, email="not-an-email")

    assert response.status_code == 422


def test_register_rejects_mismatched_passwords():
    client = TestClient(_build_app().app)

    response = _register(client, confirm_password="a different passphrase")

    assert response.status_code == 422


def test_register_rejects_missing_confirm_password():
    client = TestClient(_build_app().app)

    response = client.post(
        "/auth/register", json={"email": "dev@example.com", "password": _PASSWORD}
    )

    assert response.status_code == 422


# --- email confirmation ---


def test_verify_email_sets_session_cookies_and_returns_the_user():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register(client)

    response = _verify_latest(client, ctx.sender)

    assert response.status_code == 200
    assert response.json()["email"] == "dev@example.com"
    assert client.cookies.get("access_token")
    assert client.cookies.get("csrf_token")


def test_verify_email_marks_the_account_verified():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register(client)

    _verify_latest(client, ctx.sender)

    assert ctx.users.get_by_email("dev@example.com").email_verified is True


def test_verify_email_rejects_an_invalid_token():
    client = TestClient(_build_app().app)

    response = client.post("/auth/verify-email", json={"token": "not-a-real-token"})

    assert response.status_code == 400


# --- login ---


def test_login_is_forbidden_until_the_email_is_verified():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register(client)

    response = client.post("/auth/login", json={"email": "dev@example.com", "password": _PASSWORD})

    assert response.status_code == 403


def test_login_succeeds_after_verification():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    client.cookies.clear()

    response = client.post("/auth/login", json={"email": "dev@example.com", "password": _PASSWORD})

    assert response.status_code == 200
    assert client.cookies.get("access_token")


def test_login_with_wrong_password_is_unauthorized():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    client.cookies.clear()

    response = client.post(
        "/auth/login", json={"email": "dev@example.com", "password": "wrong wrong wrong"}
    )

    assert response.status_code == 401


# --- login rate limiting ---

_WRONG = "wrong wrong wrong"


def _fail_login(client: TestClient, email: str = "dev@example.com"):
    return client.post("/auth/login", json={"email": email, "password": _WRONG})


def test_login_is_throttled_after_repeated_failures():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    client.cookies.clear()

    # The harness allows 3 failures (see _RATE_LIMIT_ATTEMPTS); the 4th is throttled.
    for _ in range(_RATE_LIMIT_ATTEMPTS):
        assert _fail_login(client).status_code == 401

    blocked = _fail_login(client)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_throttling_is_per_email_not_global():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender, email="alice@example.com")
    _register_and_verify(client, ctx.sender, email="bob@example.com")
    client.cookies.clear()

    for _ in range(_RATE_LIMIT_ATTEMPTS + 1):
        _fail_login(client, email="alice@example.com")

    # bob is untouched even though alice (same client IP) is now blocked.
    assert _fail_login(client, email="bob@example.com").status_code == 401


def test_successful_login_resets_the_throttle_counter():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    client.cookies.clear()

    for _ in range(_RATE_LIMIT_ATTEMPTS - 1):  # stay below the limit
        assert _fail_login(client).status_code == 401

    ok = client.post("/auth/login", json={"email": "dev@example.com", "password": _PASSWORD})
    assert ok.status_code == 200
    client.cookies.clear()

    # The success cleared the counter, so further failures start from zero — without the
    # reset, the second of these would have tripped the limit.
    for _ in range(_RATE_LIMIT_ATTEMPTS - 1):
        assert _fail_login(client).status_code == 401


# --- password change ---


def _change_password(client: TestClient, current: str = _PASSWORD, new: str = _NEW_PASSWORD):
    """POST /auth/password is a mutating private route, so it needs the CSRF header."""
    return client.post(
        "/auth/password",
        json={"current_password": current, "new_password": new},
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )


def test_change_password_succeeds_and_the_new_password_logs_in():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)

    assert _change_password(client).status_code == 204

    client.cookies.clear()
    new_login = client.post(
        "/auth/login", json={"email": "dev@example.com", "password": _NEW_PASSWORD}
    )
    old_login = client.post(
        "/auth/login", json={"email": "dev@example.com", "password": _PASSWORD}
    )
    assert new_login.status_code == 200
    assert old_login.status_code == 401


def test_change_password_with_wrong_current_password_is_unauthorized():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)

    assert _change_password(client, current="not my password at all").status_code == 401


def test_change_password_invalidates_other_existing_sessions():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    stale_cookie = client.cookies.get("access_token")  # the session from before the change

    assert _change_password(client).status_code == 204

    # The current device keeps a freshly issued cookie and stays authenticated...
    assert client.get("/auth/me").status_code == 200
    # ...but any other session still holding the pre-change token is now rejected.
    other = TestClient(ctx.app)
    other.cookies.set("access_token", stale_cookie)
    assert other.get("/auth/me").status_code == 401


def test_change_password_requires_authentication():
    client = TestClient(_build_app().app)

    response = client.post(
        "/auth/password",
        json={"current_password": _PASSWORD, "new_password": _NEW_PASSWORD},
    )

    assert response.status_code == 401


# --- forgot / reset password ---


def _forgot(client: TestClient, email: str = "dev@example.com"):
    return client.post("/auth/forgot-password", json={"email": email})


def _reset(client: TestClient, token: str, new_password: str = _NEW_PASSWORD, confirm_password=None):
    return client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": new_password,
            "confirm_password": new_password if confirm_password is None else confirm_password,
        },
    )


def test_forgot_password_emails_a_reset_link_for_a_known_user():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)

    response = _forgot(client)

    assert response.status_code == 202
    reset_email = ctx.sender.sent[-1]
    assert reset_email["to"] == "dev@example.com"
    assert _RESET_LINK in reset_email["body"]


def test_forgot_password_is_accepted_but_sends_nothing_for_an_unknown_email():
    ctx = _build_app()
    client = TestClient(ctx.app)

    response = _forgot(client, email="nobody@example.com")

    # Same 202 as the known-user case (enumeration-resistant), but no email goes out.
    assert response.status_code == 202
    assert ctx.sender.sent == []


def test_forgot_password_is_throttled_after_repeated_requests():
    ctx = _build_app()
    client = TestClient(ctx.app)

    for _ in range(_RATE_LIMIT_ATTEMPTS):
        assert _forgot(client, email="someone@example.com").status_code == 202

    blocked = _forgot(client, email="someone@example.com")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_reset_password_lets_the_new_password_log_in_and_sets_a_session():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    _forgot(client)
    token = _token_from_email(ctx.sender.sent[-1]["body"])

    response = _reset(client, token)

    assert response.status_code == 200
    assert client.cookies.get("access_token")
    fresh = TestClient(ctx.app)
    assert (
        fresh.post(
            "/auth/login", json={"email": "dev@example.com", "password": _NEW_PASSWORD}
        ).status_code
        == 200
    )
    assert (
        fresh.post(
            "/auth/login", json={"email": "dev@example.com", "password": _PASSWORD}
        ).status_code
        == 401
    )


def test_reset_password_invalidates_previously_issued_sessions():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    stale_cookie = client.cookies.get("access_token")  # session from before the reset
    _forgot(client)
    token = _token_from_email(ctx.sender.sent[-1]["body"])

    _reset(client, token)

    other = TestClient(ctx.app)
    other.cookies.set("access_token", stale_cookie)
    assert other.get("/auth/me").status_code == 401


def test_reset_password_rejects_an_invalid_token():
    client = TestClient(_build_app().app)

    response = _reset(client, token="not-a-real-token")

    assert response.status_code == 400


def test_reset_password_rejects_mismatched_passwords():
    # The schema rejects the mismatch before the token is even consulted.
    client = TestClient(_build_app().app)

    response = _reset(client, token="reset:user-1", confirm_password="a different passphrase")

    assert response.status_code == 422


# --- the guard ---


def test_me_requires_authentication():
    client = TestClient(_build_app().app)

    assert client.get("/auth/me").status_code == 401


def test_me_returns_current_user_when_authenticated():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "dev@example.com"


def test_app_routes_are_guarded():
    client = TestClient(_build_app().app)

    # A protected app route returns 401 (guard runs before the route's use case).
    assert client.get("/offers/count").status_code == 401


def test_stale_token_version_is_rejected():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    stored = ctx.users.get_by_email("dev@example.com")
    # Simulate a logout-everywhere / password change: bump the user's token_version so
    # the already-issued cookie (version 0) no longer matches.
    ctx.users.add(replace(stored, token_version=stored.token_version + 1))

    assert client.get("/auth/me").status_code == 401


# --- CSRF ---


def test_mutating_request_without_csrf_header_is_forbidden():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)

    # Authenticated (cookie present) but no X-CSRF-Token header.
    assert client.post("/auth/logout").status_code == 403


def test_mutating_request_with_matching_csrf_header_succeeds():
    ctx = _build_app()
    client = TestClient(ctx.app)
    _register_and_verify(client, ctx.sender)
    csrf = client.cookies.get("csrf_token")

    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})

    assert response.status_code == 204
