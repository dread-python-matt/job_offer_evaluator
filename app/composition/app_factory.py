"""Assemble the FastAPI application from the concern builders.

`build_app()` is the single orchestration point: it configures process-wide logging and validates
config (fail-fast), builds the shared `Foundation` and each concern's components, creates the
FastAPI app with its middleware and routers, then overrides every route dependency with its
concrete implementation. `main.py` only calls this and runs the server.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.composition.ai import AiComponents, build_ai
from app.composition.auth import AuthComponents, build_auth
from app.composition.foundation import Foundation, build_foundation
from app.composition.offers import OfferUseCases, build_offer_use_cases
from app.composition.usage import UsageComponents, build_usage
from app.config import CORS_ORIGINS, COOKIE_SECURE, LLM_DEBUG, LOG_FORMAT, LOG_LEVEL
from app.config_validation import validate_runtime_config
from app.infrastructure.db_readiness import EngineReadinessProbe
from app.infrastructure.llm_logging import configure_llm_logging
from app.observability.logging_config import configure_logging
from app.presentation.api.auth import (
    get_authenticate_use_case,
    get_change_password_use_case,
    get_cookie_settings,
    get_current_user,
    get_rate_limiter,
    get_readiness_probe,
    get_refresh_token_service,
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
from app.presentation.api.error_handlers import register_exception_handlers
from app.presentation.api.request_logging import RequestLoggingMiddleware
from app.presentation.api.routes import (
    get_add_api_key_use_case,
    get_admin_key_use_case,
    get_ai_scoring_context,
    get_budget_service,
    get_calculate_salary_use_case,
    get_count_offers_use_case,
    get_daily_request_usage_use_case,
    get_delete_admin_key_use_case,
    get_delete_api_key_use_case,
    get_list_api_keys_use_case,
    get_list_available_models_use_case,
    get_list_offers_use_case,
    get_match_offers_ai_use_case,
    get_match_offers_use_case,
    get_model_usage_summary_use_case,
    get_org_spend_use_case,
    get_org_usage_use_case,
    get_profile_use_case,
    get_save_profile_use_case,
    get_set_admin_key_use_case,
    get_set_api_key_budget_use_case,
    get_set_daily_request_limit_use_case,
    router,
)
from app.presentation.api.security_headers import SecurityHeadersMiddleware


def _configure_process() -> None:
    """Process-wide setup that must run once, before anything logs or serves: structured logging
    first, then optional verbose LLM logging, then fail-fast validation of production config
    (default JWT secret, non-secure cookies, wildcard CORS)."""
    configure_logging(level=LOG_LEVEL, fmt=LOG_FORMAT)
    configure_llm_logging(LLM_DEBUG)
    validate_runtime_config()


def _configure_middleware(app: FastAPI) -> None:
    # RequestLoggingMiddleware is added last so it is outermost: it binds one correlation id per
    # request and times the whole stack (CORS + security headers included). HSTS only when cookies
    # are Secure (i.e. served over HTTPS).
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=COOKIE_SECURE)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)


def _include_routers(app: FastAPI) -> None:
    # Public endpoints (health, register, login) carry no guard; everything else — the app's API
    # plus the authenticated auth endpoints — is gated by a valid session cookie and (for unsafe
    # methods) a matching CSRF token.
    auth_guard = [Depends(get_current_user), Depends(verify_csrf)]
    app.include_router(public_router)
    app.include_router(private_router, dependencies=auth_guard)
    app.include_router(router, dependencies=auth_guard)


def _wire_dependencies(
    app: FastAPI,
    foundation: Foundation,
    offers: OfferUseCases,
    usage: UsageComponents,
    ai: AiComponents,
    auth: AuthComponents,
) -> None:
    """Override each router's placeholder provider with its concrete implementation. Constant
    providers return a fixed instance; the per-request resolvers (AI use case, org spend/usage)
    are dependency functions that read the current user, so they are registered directly."""
    overrides = app.dependency_overrides

    # Readiness (`GET /health/ready`): a real `SELECT 1`, so it returns 503 while the DB is down.
    readiness_probe = EngineReadinessProbe(foundation.engine)
    overrides[get_readiness_probe] = lambda: readiness_probe

    # --- auth ---
    overrides[get_register_use_case] = lambda: auth.register
    overrides[get_authenticate_use_case] = lambda: auth.authenticate
    overrides[get_verify_email_use_case] = lambda: auth.verify_email
    overrides[get_user_repository] = lambda: foundation.user_repository
    overrides[get_token_service] = lambda: auth.token_service
    overrides[get_refresh_token_service] = lambda: auth.refresh_token_service
    overrides[get_cookie_settings] = lambda: auth.cookie_settings
    overrides[get_rate_limiter] = lambda: auth.rate_limiter
    overrides[get_change_password_use_case] = lambda: auth.change_password
    overrides[get_request_password_reset_use_case] = lambda: auth.request_password_reset
    overrides[get_reset_password_use_case] = lambda: auth.reset_password

    # --- offers / profile / salary ---
    overrides[get_save_profile_use_case] = lambda: offers.save_profile
    overrides[get_profile_use_case] = lambda: offers.get_profile
    overrides[get_match_offers_use_case] = lambda: offers.match_offers
    overrides[get_count_offers_use_case] = lambda: offers.count_offers
    overrides[get_list_offers_use_case] = lambda: offers.list_offers
    overrides[get_calculate_salary_use_case] = lambda: offers.calculate_salary

    # --- AI matching / models / API keys ---
    overrides[get_match_offers_ai_use_case] = ai.ai_use_case_for_request
    overrides[get_ai_scoring_context] = lambda: ai.scoring_context
    overrides[get_list_available_models_use_case] = lambda: ai.list_available_models
    overrides[get_add_api_key_use_case] = lambda: ai.add_api_key
    overrides[get_list_api_keys_use_case] = lambda: ai.list_api_keys
    overrides[get_set_api_key_budget_use_case] = lambda: ai.set_api_key_budget
    overrides[get_delete_api_key_use_case] = lambda: ai.delete_api_key

    # --- usage / budget / admin key ---
    overrides[get_model_usage_summary_use_case] = lambda: usage.usage_summary
    overrides[get_budget_service] = lambda: usage.budget_service
    # Org readouts resolve per request from the caller's admin key (env fallback): functions.
    overrides[get_org_spend_use_case] = usage.org_spend_for_request
    overrides[get_org_usage_use_case] = usage.org_usage_for_request
    overrides[get_daily_request_usage_use_case] = lambda: usage.get_daily_request_usage
    overrides[get_set_daily_request_limit_use_case] = lambda: usage.set_daily_request_limit
    overrides[get_admin_key_use_case] = lambda: usage.get_admin_key
    overrides[get_set_admin_key_use_case] = lambda: usage.set_admin_key
    overrides[get_delete_admin_key_use_case] = lambda: usage.delete_admin_key


def build_app() -> FastAPI:
    _configure_process()

    foundation = build_foundation()
    offers = build_offer_use_cases(foundation)
    usage = build_usage(foundation)
    ai = build_ai(foundation, usage)
    auth = build_auth(foundation)

    app = FastAPI(title="Job Offer Matcher")
    _configure_middleware(app)
    _include_routers(app)
    register_exception_handlers(app)
    _wire_dependencies(app, foundation, offers, usage, ai, auth)
    return app
