import secrets
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.application.auth_use_cases import AuthenticateUserUseCase, RegisterUserUseCase
from app.application.ports import TokenService, UserRepository
from app.domain.auth import User
from app.domain.errors import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)
from app.presentation.api.schemas import (
    LoginRequestSchema,
    RegisterRequestSchema,
    UserResponseSchema,
)

ACCESS_COOKIE = "access_token"
CSRF_COOKIE = "csrf_token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass(frozen=True)
class CookieSettings:
    """How auth cookies are emitted. Dev (http, same-site) uses samesite='lax',
    secure=False; cross-site prod needs samesite='none', secure=True (HTTPS)."""

    secure: bool = False
    samesite: str = "lax"
    max_age: int = 7 * 24 * 3600


# --- dependency providers (overridden in main.py / tests) ---


def get_register_use_case() -> RegisterUserUseCase:
    raise NotImplementedError("override with a configured use case")


def get_authenticate_use_case() -> AuthenticateUserUseCase:
    raise NotImplementedError("override with a configured use case")


def get_user_repository() -> UserRepository:
    raise NotImplementedError("override with a configured repository")


def get_token_service() -> TokenService:
    raise NotImplementedError("override with a configured service")


def get_cookie_settings() -> CookieSettings:
    return CookieSettings()


# --- security dependencies applied to protected routers ---


def get_current_user(
    request: Request,
    tokens: TokenService = Depends(get_token_service),
    users: UserRepository = Depends(get_user_repository),
) -> User:
    """Resolve the caller from the session cookie. 401 if the cookie is absent, the
    token is invalid/expired, the user no longer exists, or its token_version is stale
    (revoked). The same opaque error is used throughout to avoid leaking which."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = tokens.verify(token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Not authenticated") from exc
    user = users.get_by_id(claims.user_id)
    if user is None or user.token_version != claims.token_version:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def verify_csrf(request: Request) -> None:
    """Double-submit CSRF check for state-changing requests: the X-CSRF-Token header
    must equal the (non-httpOnly) csrf_token cookie. Safe methods are exempt."""
    if request.method in _SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def _issue_session(response: Response, token: str, settings: CookieSettings) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=settings.max_age,
        httponly=True,
        secure=settings.secure,
        samesite=settings.samesite,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=settings.max_age,
        httponly=False,  # the SPA must read this to echo it back in the header
        secure=settings.secure,
        samesite=settings.samesite,
        path="/",
    )


def _clear_session(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


# --- routers ---

public_router = APIRouter()
private_router = APIRouter()


@public_router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for orchestration/load balancers. Intentionally dependency-free
    and unauthenticated so it stays green even if downstream providers are degraded."""
    return {"status": "ok"}


@public_router.post("/auth/register", status_code=201, response_model=UserResponseSchema)
def register(
    payload: RegisterRequestSchema,
    response: Response,
    use_case: RegisterUserUseCase = Depends(get_register_use_case),
    tokens: TokenService = Depends(get_token_service),
    settings: CookieSettings = Depends(get_cookie_settings),
) -> UserResponseSchema:
    try:
        user = use_case.execute(email=payload.email, password=payload.password)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    _issue_session(response, tokens.issue(user.id, user.token_version), settings)
    return UserResponseSchema.from_domain(user)


@public_router.post("/auth/login", response_model=UserResponseSchema)
def login(
    payload: LoginRequestSchema,
    response: Response,
    use_case: AuthenticateUserUseCase = Depends(get_authenticate_use_case),
    settings: CookieSettings = Depends(get_cookie_settings),
) -> UserResponseSchema:
    try:
        user, token = use_case.execute(email=payload.email, password=payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc
    _issue_session(response, token, settings)
    return UserResponseSchema.from_domain(user)


@private_router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    _clear_session(response)


@private_router.get("/auth/me", response_model=UserResponseSchema)
def me(user: User = Depends(get_current_user)) -> UserResponseSchema:
    return UserResponseSchema.from_domain(user)
