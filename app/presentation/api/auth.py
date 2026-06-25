import secrets
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.application.auth_use_cases import (
    AuthenticateUserUseCase,
    ChangePasswordUseCase,
    RegisterUserUseCase,
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
    VerifyEmailUseCase,
)
from app.application.ports import RateLimiter, TokenService, UserRepository
from app.domain.auth import User
from app.domain.errors import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    EmailNotDeliverableError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidVerificationTokenError,
    RateLimitExceededError,
)
from app.presentation.api.schemas import (
    ChangePasswordRequestSchema,
    ForgotPasswordRequestSchema,
    LoginRequestSchema,
    PasswordResetRequestedSchema,
    RegisterRequestSchema,
    RegistrationPendingSchema,
    ResetPasswordRequestSchema,
    UserResponseSchema,
    VerifyEmailRequestSchema,
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


def get_verify_email_use_case() -> VerifyEmailUseCase:
    raise NotImplementedError("override with a configured use case")


def get_user_repository() -> UserRepository:
    raise NotImplementedError("override with a configured repository")


def get_token_service() -> TokenService:
    raise NotImplementedError("override with a configured service")


def get_rate_limiter() -> RateLimiter:
    raise NotImplementedError("override with a configured limiter")


def get_change_password_use_case() -> ChangePasswordUseCase:
    raise NotImplementedError("override with a configured use case")


def get_request_password_reset_use_case() -> RequestPasswordResetUseCase:
    raise NotImplementedError("override with a configured use case")


def get_reset_password_use_case() -> ResetPasswordUseCase:
    raise NotImplementedError("override with a configured use case")


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


def _login_rate_limit_key(request: Request, email: str) -> str:
    """Throttle per (client IP, email): one host can't lock out arbitrary accounts, and a
    single account can't be hammered from one host. Mirrors the use case's email
    normalization so case/whitespace variants share a bucket."""
    client_ip = request.client.host if request.client else "unknown"
    return f"{client_ip}:{email.strip().lower()}"


def _password_reset_rate_limit_key(request: Request, email: str) -> str:
    """Throttle forgot-password per (client IP, email), namespaced so it shares no bucket
    with login attempts."""
    client_ip = request.client.host if request.client else "unknown"
    return f"forgot:{client_ip}:{email.strip().lower()}"


# --- routers ---

public_router = APIRouter()
private_router = APIRouter()


@public_router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for orchestration/load balancers. Intentionally dependency-free
    and unauthenticated so it stays green even if downstream providers are degraded."""
    return {"status": "ok"}


@public_router.post(
    "/auth/register", status_code=202, response_model=RegistrationPendingSchema
)
def register(
    payload: RegisterRequestSchema,
    use_case: RegisterUserUseCase = Depends(get_register_use_case),
) -> RegistrationPendingSchema:
    """Create an unverified account and email a confirmation link. No session is issued;
    the workflow is finished by following the link (see /auth/verify-email)."""
    try:
        user = use_case.execute(email=payload.email, password=payload.password)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    except EmailNotDeliverableError as exc:
        raise HTTPException(status_code=422, detail="Email address is not deliverable") from exc
    return RegistrationPendingSchema(email=user.email)


@public_router.post("/auth/verify-email", response_model=UserResponseSchema)
def verify_email(
    payload: VerifyEmailRequestSchema,
    response: Response,
    use_case: VerifyEmailUseCase = Depends(get_verify_email_use_case),
    settings: CookieSettings = Depends(get_cookie_settings),
) -> UserResponseSchema:
    """Finish registration: confirm the email from the emailed token, then log the user in
    by issuing a session (so following the link lands them authenticated)."""
    try:
        user, token = use_case.execute(payload.token)
    except InvalidVerificationTokenError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid or expired confirmation link"
        ) from exc
    _issue_session(response, token, settings)
    return UserResponseSchema.from_domain(user)


@public_router.post("/auth/login", response_model=UserResponseSchema)
def login(
    payload: LoginRequestSchema,
    request: Request,
    response: Response,
    use_case: AuthenticateUserUseCase = Depends(get_authenticate_use_case),
    settings: CookieSettings = Depends(get_cookie_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> UserResponseSchema:
    """Throttled to blunt password brute-forcing: only wrong-credential attempts count
    toward the limit, and a successful login clears the counter for that (IP, email)."""
    key = _login_rate_limit_key(request, payload.email)
    try:
        limiter.check(key)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    try:
        user, token = use_case.execute(email=payload.email, password=payload.password)
    except InvalidCredentialsError as exc:
        limiter.record_failure(key)
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc
    except EmailNotVerifiedError as exc:
        raise HTTPException(
            status_code=403, detail="Please confirm your email address before signing in"
        ) from exc
    limiter.reset(key)
    _issue_session(response, token, settings)
    return UserResponseSchema.from_domain(user)


@public_router.post(
    "/auth/forgot-password", status_code=202, response_model=PasswordResetRequestedSchema
)
def forgot_password(
    payload: ForgotPasswordRequestSchema,
    request: Request,
    use_case: RequestPasswordResetUseCase = Depends(get_request_password_reset_use_case),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> PasswordResetRequestedSchema:
    """Email a password-reset link if the address belongs to an account. Always returns the
    same 202 (enumeration-resistant) and is throttled per (IP, email) to curb email abuse."""
    key = _password_reset_rate_limit_key(request, payload.email)
    try:
        limiter.check(key)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many reset requests. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    limiter.record_failure(key)  # every request counts toward the throttle
    use_case.execute(email=payload.email)
    return PasswordResetRequestedSchema()


@public_router.post("/auth/reset-password", response_model=UserResponseSchema)
def reset_password(
    payload: ResetPasswordRequestSchema,
    response: Response,
    use_case: ResetPasswordUseCase = Depends(get_reset_password_use_case),
    settings: CookieSettings = Depends(get_cookie_settings),
) -> UserResponseSchema:
    """Set a new password from the emailed token. Invalidates other sessions and issues a
    fresh one, so following the link lands the user signed in."""
    try:
        user, token = use_case.execute(payload.token, new_password=payload.new_password)
    except InvalidPasswordResetTokenError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link") from exc
    _issue_session(response, token, settings)
    return UserResponseSchema.from_domain(user)


@private_router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    _clear_session(response)


@private_router.get("/auth/me", response_model=UserResponseSchema)
def me(user: User = Depends(get_current_user)) -> UserResponseSchema:
    return UserResponseSchema.from_domain(user)


@private_router.post("/auth/password", status_code=204)
def change_password(
    payload: ChangePasswordRequestSchema,
    response: Response,
    user: User = Depends(get_current_user),
    use_case: ChangePasswordUseCase = Depends(get_change_password_use_case),
    settings: CookieSettings = Depends(get_cookie_settings),
) -> None:
    """Change the signed-in user's password. Bumping token_version logs out every other
    session; a fresh session cookie is re-issued here so the current device stays signed in."""
    try:
        _, token = use_case.execute(
            user_id=user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="Current password is incorrect") from exc
    _issue_session(response, token, settings)
