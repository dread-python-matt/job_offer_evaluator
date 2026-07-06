"""Composition of authentication: password hashing, JWT access/verification/reset token
services, email delivery (SMTP or a console fallback), session-cookie settings, the login
brute-force rate limiter, rotating refresh tokens, and the auth use cases. Depends on the
shared `Foundation` for the user and refresh-token repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.application.auth_use_cases import (
    AuthenticateUserUseCase,
    ChangePasswordUseCase,
    RegisterUserUseCase,
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
    VerifyEmailUseCase,
)
from app.application.ports import RateLimiter
from app.application.refresh_tokens import RefreshTokenService
from app.composition.foundation import Foundation
from app.config import (
    ACCESS_TOKEN_TTL_MINUTES,
    APP_BASE_URL,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    EMAIL_CHECK_DELIVERABILITY,
    EMAIL_FROM,
    EMAIL_VERIFICATION_TTL_HOURS,
    JWT_SECRET,
    LOGIN_RATE_LIMIT_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_MINUTES,
    PASSWORD_RESET_TTL_HOURS,
    RATE_LIMITER_BACKEND,
    REDIS_URL,
    REFRESH_TOKEN_TTL_DAYS,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)
from app.infrastructure.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.console_email_sender import ConsoleEmailSender
from app.infrastructure.email_validators import AllowAllEmailValidator, DnsEmailValidator
from app.infrastructure.in_memory_rate_limiter import InMemoryRateLimiter
from app.infrastructure.jwt_password_reset_token_service import JwtPasswordResetTokenService
from app.infrastructure.jwt_token_service import JwtTokenService
from app.infrastructure.jwt_verification_token_service import JwtVerificationTokenService
from app.infrastructure.redis_rate_limiter import RedisRateLimiter
from app.infrastructure.smtp_email_sender import SmtpEmailSender
from app.presentation.api.auth import CookieSettings


@dataclass(frozen=True)
class AuthComponents:
    register: RegisterUserUseCase
    authenticate: AuthenticateUserUseCase
    verify_email: VerifyEmailUseCase
    change_password: ChangePasswordUseCase
    request_password_reset: RequestPasswordResetUseCase
    reset_password: ResetPasswordUseCase
    token_service: JwtTokenService
    refresh_token_service: RefreshTokenService
    rate_limiter: RateLimiter
    cookie_settings: CookieSettings


def _build_email_sender() -> SmtpEmailSender | ConsoleEmailSender:
    """SMTP when configured; otherwise a console fallback that only logs the link (dev)."""
    if SMTP_HOST:
        return SmtpEmailSender(
            host=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            from_addr=EMAIL_FROM,
            use_tls=SMTP_USE_TLS,
        )
    return ConsoleEmailSender()


def _build_rate_limiter() -> RateLimiter:
    """In-memory (per-process, single-worker correct) or a shared Redis store for multi-worker
    deployments (`RATE_LIMITER_BACKEND=redis`). Same port either way — only the adapter changes."""
    window = timedelta(minutes=LOGIN_RATE_LIMIT_WINDOW_MINUTES)
    if RATE_LIMITER_BACKEND == "redis":
        import redis  # optional dependency, imported only for the redis backend

        return RedisRateLimiter(
            redis.from_url(REDIS_URL),
            max_attempts=LOGIN_RATE_LIMIT_ATTEMPTS,
            window=window,
        )
    return InMemoryRateLimiter(max_attempts=LOGIN_RATE_LIMIT_ATTEMPTS, window=window)


def build_auth(foundation: Foundation) -> AuthComponents:
    users = foundation.user_repository
    hasher = Argon2PasswordHasher()
    token_service = JwtTokenService(JWT_SECRET, ttl=timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES))
    verification_tokens = JwtVerificationTokenService(
        JWT_SECRET, ttl=timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS)
    )
    reset_tokens = JwtPasswordResetTokenService(
        JWT_SECRET, ttl=timedelta(hours=PASSWORD_RESET_TTL_HOURS)
    )
    email_sender = _build_email_sender()
    email_validator = (
        DnsEmailValidator() if EMAIL_CHECK_DELIVERABILITY else AllowAllEmailValidator()
    )

    return AuthComponents(
        register=RegisterUserUseCase(
            users,
            hasher,
            email_validator=email_validator,
            verification_tokens=verification_tokens,
            email_sender=email_sender,
            link_builder=lambda token: f"{APP_BASE_URL}/verify-email?token={token}",
        ),
        authenticate=AuthenticateUserUseCase(users, hasher, token_service),
        verify_email=VerifyEmailUseCase(users, verification_tokens, token_service),
        change_password=ChangePasswordUseCase(users, hasher, token_service),
        request_password_reset=RequestPasswordResetUseCase(
            users,
            reset_tokens,
            email_sender,
            link_builder=lambda token: f"{APP_BASE_URL}/reset-password?token={token}",
        ),
        reset_password=ResetPasswordUseCase(users, reset_tokens, hasher, token_service),
        token_service=token_service,
        refresh_token_service=RefreshTokenService(
            foundation.refresh_token_repository, ttl=timedelta(days=REFRESH_TOKEN_TTL_DAYS)
        ),
        rate_limiter=_build_rate_limiter(),
        cookie_settings=CookieSettings(
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=REFRESH_TOKEN_TTL_DAYS * 24 * 3600,
        ),
    )
