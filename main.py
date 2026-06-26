import logging
from datetime import timedelta

from agents import set_tracing_disabled
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.ai_scoring_context import AiScoringContext
from app.application.auth_use_cases import (
    AuthenticateUserUseCase,
    ChangePasswordUseCase,
    RegisterUserUseCase,
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
    VerifyEmailUseCase,
)
from app.application.api_key_use_cases import (
    AddApiKeyUseCase,
    DeleteApiKeyUseCase,
    ListApiKeysUseCase,
    SetApiKeyBudgetUseCase,
)
from app.application.api_key_resolver import UserApiKeyResolver
from app.application.budget_service import BudgetService
from app.application.refresh_tokens import RefreshTokenService
from app.application.use_cases import (
    CalculateNetSalaryUseCase,
    CountOffersUseCase,
    GetModelUsageSummaryUseCase,
    GetOrgSpendUseCase,
    GetUserProfileUseCase,
    ListAvailableModelsUseCase,
    ListOffersUseCase,
    MatchOffersUseCase,
    MatchOffersWithAiUseCase,
    SaveUserProfileUseCase,
)
from app.config import (
    ACCESS_TOKEN_TTL_MINUTES,
    AI_MATCH_CONCURRENCY,
    API_KEY_ENCRYPTION_KEY,
    APP_BASE_URL,
    BUDGET_FAIL_CLOSED,
    BUDGET_SPEND_CACHE_TTL_SECONDS,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    CORS_ORIGINS,
    DATABASE_URL,
    DB_MAX_OVERFLOW,
    DB_POOL_SIZE,
    DEFAULT_BUDGET_USD,
    GOOGLE_RPM_LIMIT,
    EMAIL_CHECK_DELIVERABILITY,
    EMAIL_FROM,
    EMAIL_VERIFICATION_TTL_HOURS,
    GEMINI_API_KEY,
    HOST,
    JWT_SECRET,
    LLM_DEBUG,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    LOGIN_RATE_LIMIT_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_MINUTES,
    MODELS_CACHE_TTL_SECONDS,
    OPENAI_ADMIN_KEY,
    OPENAI_API_KEY,
    PASSWORD_RESET_TTL_HOURS,
    PORT,
    RATE_LIMITER_BACKEND,
    REDIS_URL,
    REFRESH_TOKEN_TTL_DAYS,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
    WORKERS,
)
from app.config_validation import validate_runtime_config
from app.domain.api_providers import provider_for_company
from app.domain.auth import User
from app.domain.errors import MissingProviderApiKeyError
from app.domain.filters import FilterChain
from app.domain.salary_calculator import SalaryCalculator
from app.infrastructure.llm_utils import company_from_model
from app.infrastructure.rate_limiting import AsyncRateLimiter, TokenBucketRateLimiter
from app.infrastructure.composite_budget_status_reader import CompositeBudgetStatusReader
from app.infrastructure.db import build_engine
from app.application.ports import RateLimiter
from app.infrastructure.in_memory_rate_limiter import InMemoryRateLimiter
from app.infrastructure.redis_rate_limiter import RedisRateLimiter
from app.infrastructure.agent_models import build_chat_model_with_key
from app.infrastructure.api_key_budget_status_reader import ApiKeyBudgetStatusReader
from app.infrastructure.caching_ai_scorer import CachingAiScorer
from app.infrastructure.keyed_user_available_models_provider import (
    CachingUserAvailableModelsProvider,
    KeyedUserAvailableModelsProvider,
)
from app.infrastructure.gemini_available_models_provider import GeminiAvailableModelsProvider
from app.infrastructure.llm_logging import configure_llm_logging
from app.infrastructure.llm_provider_factory import build_llm_provider_factory
from app.infrastructure.llm_scoring_strategy import LLMScoringStrategy
from app.infrastructure.openai_available_models_provider import OpenAIAvailableModelsProvider
from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
from app.infrastructure.model_pricing_registry import HardcodedModelPricingRegistry
from app.infrastructure.org_spend_backstop import OrgSpendBackstop
from app.infrastructure.request_scoped_usage_tracker import RequestScopedModelUsageTracker
from app.infrastructure.token_accounting_spend_provider import TokenAccountingSpendProvider
from app.infrastructure.offer_filters import (
    ExpiredFilter,
    LevelFilter,
    LocationFilter,
    SalaryFilter,
    SkillFilter,
)
from app.infrastructure.postgres_ai_score_repository import PostgresAiScoreRepository
from app.infrastructure.postgres_budget_repository import PostgresBudgetRepository
from app.infrastructure.postgres_model_usage_repository import PostgresModelUsageRepository
from app.infrastructure.pricing_model_usage_repository import PricingModelUsageRepository
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.postgres_selected_model_repository import PostgresSelectedModelRepository
from app.infrastructure.postgres_user_profile_repository import PostgresUserProfileRepository
from app.infrastructure.postgres_refresh_token_repository import PostgresRefreshTokenRepository
from app.infrastructure.postgres_user_repository import PostgresUserRepository
from app.infrastructure.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from app.infrastructure.model_listing_api_key_validator import ModelListingApiKeyValidator
from app.infrastructure.postgres_api_key_repository import PostgresApiKeyRepository
from app.infrastructure.token_accounting_provider_spend_provider import (
    TokenAccountingProviderSpendProvider,
)
from app.infrastructure.console_email_sender import ConsoleEmailSender
from app.infrastructure.email_validators import AllowAllEmailValidator, DnsEmailValidator
from app.infrastructure.jwt_password_reset_token_service import JwtPasswordResetTokenService
from app.infrastructure.jwt_token_service import JwtTokenService
from app.infrastructure.jwt_verification_token_service import JwtVerificationTokenService
from app.infrastructure.smtp_email_sender import SmtpEmailSender
from app.infrastructure.scoring_strategies import SkillBasedScorer
from app.infrastructure.translation_agents import build_polish_to_english_agent
from app.presentation.api.routes import (
    get_add_api_key_use_case,
    get_ai_scoring_context,
    get_calculate_salary_use_case,
    get_budget_service,
    get_delete_api_key_use_case,
    get_list_api_keys_use_case,
    get_org_spend_use_case,
    get_set_api_key_budget_use_case,
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
from app.presentation.api.error_handlers import register_exception_handlers
from app.presentation.api.security_headers import SecurityHeadersMiddleware
from app.presentation.api.auth import (
    CookieSettings,
    get_authenticate_use_case,
    get_change_password_use_case,
    get_cookie_settings,
    get_current_user,
    get_rate_limiter,
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

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

configure_llm_logging(LLM_DEBUG)

# Fail fast before touching the DB or accepting traffic if production config is insecure
# (default JWT secret, non-secure cookies, wildcard CORS); warns on multi-worker setups.
validate_runtime_config()

# LLM_PROVIDER still selects org-level usage/cost wiring; the scoring model itself
# is chosen by the user via the API (and the SDK is reconfigured per model below).
_llm_factory = build_llm_provider_factory(
    LLM_PROVIDER, OPENAI_API_KEY, OPENAI_ADMIN_KEY, GEMINI_API_KEY
)

_engine = build_engine(DATABASE_URL, pool_size=DB_POOL_SIZE, max_overflow=DB_MAX_OVERFLOW)
profile_repository = PostgresUserProfileRepository(_engine)
offer_repository = PostgresOfferRepository(_engine)
filter_chain = FilterChain(
    [SkillFilter(), LocationFilter(), SalaryFilter(), ExpiredFilter(), LevelFilter()]
)
# Pricing is applied once at write time and frozen onto each row's cost_usd, so a later price
# change never rewrites historical spend and spend reads just sum the stored column.
model_usage_repository = PricingModelUsageRepository(
    PostgresModelUsageRepository(_engine), HardcodedModelPricingRegistry()
)

save_profile_use_case = SaveUserProfileUseCase(profile_repository)
get_user_profile_use_case = GetUserProfileUseCase(profile_repository)
count_offers_use_case = CountOffersUseCase(offer_repository)
list_offers_use_case = ListOffersUseCase(offer_repository)
match_offers_use_case = MatchOffersUseCase(offer_repository, SkillBasedScorer(), filter_chain)
# Scorers record token usage into this request-scoped tracker; the AI match use case opens
# a fresh scope per request (begin()), then drains it, stamps the calling user, and persists
# it. Request scoping (contextvars) keeps concurrent matches from mis-attributing tokens
# across users/requests.
_in_memory_tracker = RequestScopedModelUsageTracker()


_ai_score_repository = PostgresAiScoreRepository(_engine)
_selected_model_repository = PostgresSelectedModelRepository(_engine)
_budget_repository = PostgresBudgetRepository(_engine, default_limit_usd=DEFAULT_BUDGET_USD)
# A user's budget is enforced from their own recorded token usage, summing the cost snapshotted
# onto each row at write time.
_user_spend_provider = TokenAccountingSpendProvider(model_usage_repository)
_budget_service = BudgetService(
    _budget_repository,
    _user_spend_provider,
    cache_ttl_seconds=BUDGET_SPEND_CACHE_TTL_SECONDS,
)

# --- User-supplied provider API keys (each with its own budget) ---
# Keys are encrypted at rest (the server must replay them, so encryption not hashing) and
# validated against the provider — by listing models, which is free — before being stored.
_api_key_repository = PostgresApiKeyRepository(_engine)
_key_cipher = FernetKeyCipher(API_KEY_ENCRYPTION_KEY)


def _models_provider_for_key(provider: str, key: str):
    if provider == "google":
        return GeminiAvailableModelsProvider(key, timeout=LLM_TIMEOUT_SECONDS)
    return OpenAIAvailableModelsProvider(key, timeout=LLM_TIMEOUT_SECONDS)


_api_key_validator = ModelListingApiKeyValidator(provider_factory=_models_provider_for_key)
# Each key's usage is derived per provider from the user's recorded usage, summing each row's
# write-time cost snapshot for that provider's models.
_provider_spend_provider = TokenAccountingProviderSpendProvider(model_usage_repository)
_list_api_keys_use_case = ListApiKeysUseCase(_api_key_repository, _provider_spend_provider)
_set_api_key_budget_use_case = SetApiKeyBudgetUseCase(_api_key_repository, _provider_spend_provider)
# Scoring resolves the calling user's own key on demand (require own key — no env fallback).
_api_key_resolver = UserApiKeyResolver(_api_key_repository, _key_cipher)
# The model picker is per-user: discovered from the user's own keys, cached per user.
_user_available_models_provider = CachingUserAvailableModelsProvider(
    KeyedUserAvailableModelsProvider(_api_key_repository, _key_cipher, _models_provider_for_key),
    ttl_seconds=MODELS_CACHE_TTL_SECONDS,
)
# Adding/removing/rotating a key changes which providers the user can pick AND any cached AI
# use case bound to a now-stale key, so a key change must invalidate both per-user caches:
# the model picker (else a freshly added provider stays hidden until the TTL) and the AI
# scoring context (else a rotated key keeps replaying the deleted credential until restart).
# `_ai_scoring_context` is assigned later in this module; this only runs at request time, by
# which point it is always defined (late binding).
def _on_user_keys_changed(user_id: str) -> None:
    _user_available_models_provider.invalidate(user_id)
    _ai_scoring_context.invalidate(user_id)


_add_api_key_use_case = AddApiKeyUseCase(
    _api_key_repository,
    _key_cipher,
    _api_key_validator,
    on_change=_on_user_keys_changed,
)
_delete_api_key_use_case = DeleteApiKeyUseCase(
    _api_key_repository, on_change=_on_user_keys_changed
)
# AI matches are gated by the model's own provider key budget (per-key spend vs that key's
# limit) plus a global org-spend backstop that protects the owner's actual provider bill
# (active only when an admin key is configured). The per-key reader is bound per build (it
# depends on the scored model's provider); the org backstop is user-independent, built once.
_org_spend_provider = _llm_factory.build_spend_provider()
_org_spend_backstop = OrgSpendBackstop(_org_spend_provider, DEFAULT_BUDGET_USD)
# Org-level real-$ spend readout (admin key); None provider → endpoint returns null.
_get_org_spend_use_case = GetOrgSpendUseCase(_org_spend_provider)


def _build_budget_gate(api_provider: str | None) -> CompositeBudgetStatusReader:
    readers: list = []
    if api_provider is not None:
        readers.append(
            ApiKeyBudgetStatusReader(_api_key_repository, _provider_spend_provider, api_provider)
        )
    readers.append(_org_spend_backstop)
    return CompositeBudgetStatusReader(readers)

_user_repository = PostgresUserRepository(_engine)
_password_hasher = Argon2PasswordHasher()
_token_service = JwtTokenService(JWT_SECRET, ttl=timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES))
# Email confirmation: unverified accounts receive a single-purpose token by email; following
# the link verifies the account and logs the user in (see /auth/verify-email).
_verification_token_service = JwtVerificationTokenService(
    JWT_SECRET, ttl=timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS)
)
# Password reset uses its own single-purpose token (distinct from confirmation tokens).
_password_reset_token_service = JwtPasswordResetTokenService(
    JWT_SECRET, ttl=timedelta(hours=PASSWORD_RESET_TTL_HOURS)
)
_email_sender = (
    SmtpEmailSender(
        host=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USERNAME,
        password=SMTP_PASSWORD,
        from_addr=EMAIL_FROM,
        use_tls=SMTP_USE_TLS,
    )
    if SMTP_HOST
    else ConsoleEmailSender()
)
_email_validator = DnsEmailValidator() if EMAIL_CHECK_DELIVERABILITY else AllowAllEmailValidator()


def _verification_link(token: str) -> str:
    return f"{APP_BASE_URL}/verify-email?token={token}"


_register_use_case = RegisterUserUseCase(
    _user_repository,
    _password_hasher,
    email_validator=_email_validator,
    verification_tokens=_verification_token_service,
    email_sender=_email_sender,
    link_builder=_verification_link,
)
_authenticate_use_case = AuthenticateUserUseCase(_user_repository, _password_hasher, _token_service)
_verify_email_use_case = VerifyEmailUseCase(
    _user_repository, _verification_token_service, _token_service
)
_change_password_use_case = ChangePasswordUseCase(
    _user_repository, _password_hasher, _token_service
)


def _reset_link(token: str) -> str:
    return f"{APP_BASE_URL}/reset-password?token={token}"


_request_password_reset_use_case = RequestPasswordResetUseCase(
    _user_repository,
    _password_reset_token_service,
    _email_sender,
    link_builder=_reset_link,
)
_reset_password_use_case = ResetPasswordUseCase(
    _user_repository, _password_reset_token_service, _password_hasher, _token_service
)
_cookie_settings = CookieSettings(
    secure=COOKIE_SECURE,
    samesite=COOKIE_SAMESITE,
    max_age=REFRESH_TOKEN_TTL_DAYS * 24 * 3600,
)
# Rotating, reuse-detecting refresh tokens (RFC 9700): the short-lived access token is
# exchanged at /auth/refresh for a fresh one; replaying a consumed token burns the family.
_refresh_token_service = RefreshTokenService(
    PostgresRefreshTokenRepository(_engine),
    ttl=timedelta(days=REFRESH_TOKEN_TTL_DAYS),
)
# Brute-force throttle for /auth/login + /auth/forgot-password. In-memory is per-process
# (single-worker correct); RATE_LIMITER_BACKEND=redis swaps in a store shared across all
# workers/instances. Same port either way — only the adapter changes.
def _build_rate_limiter() -> RateLimiter:
    window = timedelta(minutes=LOGIN_RATE_LIMIT_WINDOW_MINUTES)
    if RATE_LIMITER_BACKEND == "redis":
        import redis  # optional dependency, imported only for the redis backend

        return RedisRateLimiter(
            redis.from_url(REDIS_URL),
            max_attempts=LOGIN_RATE_LIMIT_ATTEMPTS,
            window=window,
        )
    return InMemoryRateLimiter(max_attempts=LOGIN_RATE_LIMIT_ATTEMPTS, window=window)


_rate_limiter = _build_rate_limiter()


def _disable_tracing(_model: str) -> None:
    # Each use case now builds agents with their own per-model client (build_chat_model),
    # so model selection no longer mutates the global SDK client. Only tracing needs
    # disabling globally (idempotent) — there's no tracing backend configured.
    set_tracing_disabled(True)


def _provider_for_model(model: str) -> str:
    """The provider id for a model, or raise MissingProviderApiKeyError when the model is
    from a company the user can't key (so it's reported as 'add a key')."""
    provider = provider_for_company(company_from_model(model))
    if provider is None:
        raise MissingProviderApiKeyError(company_from_model(model))
    return provider


# One Google rate limiter per user: Gemini free-tier limits are per project (the user's own
# key), so each user paces independently. Shared across that user's cached scorers so two
# Google models don't each get a full RPM budget against the one project quota.
_google_rate_limiters: dict[str, AsyncRateLimiter] = {}


def _google_rate_limiter_for(user_id: str) -> AsyncRateLimiter | None:
    """The user's Google pacing limiter, or None when pacing is disabled (GOOGLE_RPM_LIMIT=0).
    OpenAI scoring is never paced — only Google's stricter free tier needs it."""
    if GOOGLE_RPM_LIMIT <= 0:
        return None
    if user_id not in _google_rate_limiters:
        _google_rate_limiters[user_id] = TokenBucketRateLimiter(GOOGLE_RPM_LIMIT)
    return _google_rate_limiters[user_id]


def _build_ai_use_case(user_id: str, model: str) -> MatchOffersWithAiUseCase:
    rate_limiter: AsyncRateLimiter | None = None
    if model:
        provider = _provider_for_model(model)
        key = _api_key_resolver.key_for_provider(user_id, provider)  # require own key
        chat_model = build_chat_model_with_key(model, api_key=key, timeout=LLM_TIMEOUT_SECONDS)
        budget_gate = _build_budget_gate(provider)
        if company_from_model(model) == "Google":
            rate_limiter = _google_rate_limiter_for(user_id)  # pace under the free-tier RPM cap
    else:
        chat_model = None
        budget_gate = _build_budget_gate(None)
    ai_scorer = CachingAiScorer(
        LLMScoringStrategy.create(
            model=model,
            chat_model=chat_model,
            translator_agent=build_polish_to_english_agent(chat_model=chat_model),
            usage_tracker=_in_memory_tracker,
            rate_limiter=rate_limiter,
        ),
        _ai_score_repository,
        model=model,
    )
    return MatchOffersWithAiUseCase(
        offer_repository,
        filter_chain,
        SkillBasedScorer(),
        ai_scorer,
        usage_tracker=_in_memory_tracker,
        usage_repository=model_usage_repository,
        budget=budget_gate,
        max_concurrency=AI_MATCH_CONCURRENCY,
        fail_closed=BUDGET_FAIL_CLOSED,
    )


# Each user must select a model from their own keys; there is no global default model.
set_tracing_disabled(True)

_ai_scoring_context = AiScoringContext(
    repository=_selected_model_repository,
    build_use_case=_build_ai_use_case,
    configure_sdk=_disable_tracing,
    default_model="",
)


def _ai_use_case_for_request(user: User = Depends(get_current_user)) -> MatchOffersWithAiUseCase:
    """Resolve the AI match use case for the calling user's selected model (per-user)."""
    return _ai_scoring_context.use_case_for(user.id)


calculate_salary_use_case = CalculateNetSalaryUseCase(SalaryCalculator())
get_model_usage_summary_use_case_instance = GetModelUsageSummaryUseCase(
    model_usage_repository, HardcodedModelLimitsRegistry()
)

app = FastAPI(title="Job Offer Matcher")
# Defense-in-depth response headers (HSTS only when cookies are Secure, i.e. served over HTTPS).
app.add_middleware(SecurityHeadersMiddleware, enable_hsts=COOKIE_SECURE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Public endpoints (health, register, login) carry no auth guard. Everything else —
# the app's API plus the authenticated auth endpoints (logout, me) — is gated by a
# valid session cookie and (for unsafe methods) a matching CSRF token.
_auth_guard = [Depends(get_current_user), Depends(verify_csrf)]
app.include_router(public_router)
app.include_router(private_router, dependencies=_auth_guard)
app.include_router(router, dependencies=_auth_guard)
register_exception_handlers(app)
app.dependency_overrides[get_register_use_case] = lambda: _register_use_case
app.dependency_overrides[get_authenticate_use_case] = lambda: _authenticate_use_case
app.dependency_overrides[get_verify_email_use_case] = lambda: _verify_email_use_case
app.dependency_overrides[get_user_repository] = lambda: _user_repository
app.dependency_overrides[get_token_service] = lambda: _token_service
app.dependency_overrides[get_refresh_token_service] = lambda: _refresh_token_service
app.dependency_overrides[get_cookie_settings] = lambda: _cookie_settings
app.dependency_overrides[get_rate_limiter] = lambda: _rate_limiter
app.dependency_overrides[get_change_password_use_case] = lambda: _change_password_use_case
app.dependency_overrides[get_request_password_reset_use_case] = lambda: _request_password_reset_use_case
app.dependency_overrides[get_reset_password_use_case] = lambda: _reset_password_use_case
app.dependency_overrides[get_save_profile_use_case] = lambda: save_profile_use_case
app.dependency_overrides[get_profile_use_case] = lambda: get_user_profile_use_case
app.dependency_overrides[get_match_offers_use_case] = lambda: match_offers_use_case
app.dependency_overrides[get_match_offers_ai_use_case] = _ai_use_case_for_request
app.dependency_overrides[get_ai_scoring_context] = lambda: _ai_scoring_context
app.dependency_overrides[get_list_available_models_use_case] = lambda: ListAvailableModelsUseCase(_user_available_models_provider)
app.dependency_overrides[get_count_offers_use_case] = lambda: count_offers_use_case
app.dependency_overrides[get_list_offers_use_case] = lambda: list_offers_use_case
app.dependency_overrides[get_calculate_salary_use_case] = lambda: calculate_salary_use_case
app.dependency_overrides[get_model_usage_summary_use_case] = lambda: get_model_usage_summary_use_case_instance
app.dependency_overrides[get_budget_service] = lambda: _budget_service
app.dependency_overrides[get_org_spend_use_case] = lambda: _get_org_spend_use_case
app.dependency_overrides[get_add_api_key_use_case] = lambda: _add_api_key_use_case
app.dependency_overrides[get_list_api_keys_use_case] = lambda: _list_api_keys_use_case
app.dependency_overrides[get_set_api_key_budget_use_case] = lambda: _set_api_key_budget_use_case
app.dependency_overrides[get_delete_api_key_use_case] = lambda: _delete_api_key_use_case


def main() -> None:
    import uvicorn

    if WORKERS > 1:
        # Multiple workers require an import string so uvicorn can spawn processes.
        uvicorn.run("main:app", host=HOST, port=PORT, workers=WORKERS)
    else:
        uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
