import logging
from datetime import timedelta

from agents import set_tracing_disabled
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.ai_scoring_context import AiScoringContext
from app.application.auth_use_cases import AuthenticateUserUseCase, RegisterUserUseCase
from app.application.budget_service import BudgetService
from app.application.ports import InMemoryModelUsageTracker
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
from app.config import (
    AI_MATCH_CONCURRENCY,
    BUDGET_FAIL_CLOSED,
    BUDGET_SPEND_CACHE_TTL_SECONDS,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    CORS_ORIGINS,
    DATABASE_URL,
    DEFAULT_BUDGET_USD,
    GEMINI_API_KEY,
    HOST,
    JWT_SECRET,
    LLM_DEBUG,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    MODELS_CACHE_TTL_SECONDS,
    OPENAI_ADMIN_KEY,
    OPENAI_API_KEY,
    PORT,
    SESSION_TTL_DAYS,
    WORKERS,
)
from app.domain.auth import User
from app.domain.filters import FilterChain
from app.domain.salary_calculator import SalaryCalculator
from app.infrastructure.caching_available_models_provider import CachingAvailableModelsProvider
from app.infrastructure.composite_budget_status_reader import CompositeBudgetStatusReader
from app.infrastructure.db import build_engine
from app.infrastructure.composite_available_models_provider import CompositeAvailableModelsProvider
from app.infrastructure.agent_models import build_chat_model
from app.infrastructure.caching_ai_scorer import CachingAiScorer
from app.infrastructure.gemini_available_models_provider import GeminiAvailableModelsProvider
from app.infrastructure.llm_logging import configure_llm_logging
from app.infrastructure.llm_provider_factory import build_llm_provider_factory
from app.infrastructure.llm_scoring_strategy import LLMScoringStrategy
from app.infrastructure.openai_available_models_provider import OpenAIAvailableModelsProvider
from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
from app.infrastructure.model_pricing_registry import HardcodedModelPricingRegistry
from app.infrastructure.org_spend_backstop import OrgSpendBackstop
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
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.postgres_selected_model_repository import PostgresSelectedModelRepository
from app.infrastructure.postgres_user_profile_repository import PostgresUserProfileRepository
from app.infrastructure.postgres_user_repository import PostgresUserRepository
from app.infrastructure.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.jwt_token_service import JwtTokenService
from app.infrastructure.scoring_strategies import SkillBasedScorer
from app.infrastructure.translation_agents import build_polish_to_english_agent
from app.presentation.api.routes import (
    get_ai_scoring_context,
    get_calculate_salary_use_case,
    get_budget_service,
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

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

configure_llm_logging(LLM_DEBUG)

# LLM_PROVIDER still selects org-level usage/cost wiring; the scoring model itself
# is chosen by the user via the API (and the SDK is reconfigured per model below).
_llm_factory = build_llm_provider_factory(
    LLM_PROVIDER, OPENAI_API_KEY, OPENAI_ADMIN_KEY, GEMINI_API_KEY
)

_engine = build_engine(DATABASE_URL)
profile_repository = PostgresUserProfileRepository(_engine)
offer_repository = PostgresOfferRepository(_engine)
filter_chain = FilterChain(
    [SkillFilter(), LocationFilter(), SalaryFilter(), ExpiredFilter(), LevelFilter()]
)
model_usage_repository = PostgresModelUsageRepository(_engine)

save_profile_use_case = SaveUserProfileUseCase(profile_repository)
get_user_profile_use_case = GetUserProfileUseCase(profile_repository)
count_offers_use_case = CountOffersUseCase(offer_repository)
list_offers_use_case = ListOffersUseCase(offer_repository)
match_offers_use_case = MatchOffersUseCase(offer_repository, SkillBasedScorer(), filter_chain)
# Scorers record token usage into this in-process tracker; the AI match use case drains
# it per request, stamps the calling user, and persists it (per-user attribution).
_in_memory_tracker = InMemoryModelUsageTracker()


_ai_score_repository = PostgresAiScoreRepository(_engine)
_selected_model_repository = PostgresSelectedModelRepository(_engine)
_budget_repository = PostgresBudgetRepository(_engine, default_limit_usd=DEFAULT_BUDGET_USD)
# A user's budget is enforced from their own recorded token usage priced by the registry.
_user_spend_provider = TokenAccountingSpendProvider(
    model_usage_repository, HardcodedModelPricingRegistry()
)
_budget_service = BudgetService(
    _budget_repository,
    _user_spend_provider,
    cache_ttl_seconds=BUDGET_SPEND_CACHE_TTL_SECONDS,
)
# AI matches are gated by the user's token budget plus a global org-spend backstop that
# protects the owner's actual provider bill (active only when an admin key is configured).
_budget_gate = CompositeBudgetStatusReader([
    _budget_service,
    OrgSpendBackstop(_llm_factory.build_spend_provider(), DEFAULT_BUDGET_USD),
])

_user_repository = PostgresUserRepository(_engine)
_password_hasher = Argon2PasswordHasher()
_token_service = JwtTokenService(JWT_SECRET, ttl=timedelta(days=SESSION_TTL_DAYS))
_register_use_case = RegisterUserUseCase(_user_repository, _password_hasher)
_authenticate_use_case = AuthenticateUserUseCase(_user_repository, _password_hasher, _token_service)
_cookie_settings = CookieSettings(
    secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=SESSION_TTL_DAYS * 24 * 3600
)


def _disable_tracing(_model: str) -> None:
    # Each use case now builds agents with their own per-model client (build_chat_model),
    # so model selection no longer mutates the global SDK client. Only tracing needs
    # disabling globally (idempotent) — there's no tracing backend configured.
    set_tracing_disabled(True)


def _build_ai_use_case(model: str) -> MatchOffersWithAiUseCase:
    chat_model = (
        build_chat_model(
            model,
            openai_api_key=OPENAI_API_KEY,
            gemini_api_key=GEMINI_API_KEY,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        if model
        else None
    )
    ai_scorer = CachingAiScorer(
        LLMScoringStrategy.create(
            model=model,
            chat_model=chat_model,
            translator_agent=build_polish_to_english_agent(chat_model=chat_model),
            usage_tracker=_in_memory_tracker,
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
        budget=_budget_gate,
        max_concurrency=AI_MATCH_CONCURRENCY,
        fail_closed=BUDGET_FAIL_CLOSED,
    )


_available_models_provider = CachingAvailableModelsProvider(
    CompositeAvailableModelsProvider([
        provider
        for provider, key in [
            (GeminiAvailableModelsProvider(GEMINI_API_KEY, timeout=LLM_TIMEOUT_SECONDS), GEMINI_API_KEY),
            (OpenAIAvailableModelsProvider(OPENAI_API_KEY, timeout=LLM_TIMEOUT_SECONDS), OPENAI_API_KEY),
        ]
        if key
    ]),
    ttl_seconds=MODELS_CACHE_TTL_SECONDS,
)


def _pick_initial_model() -> str:
    """The scoring model is user-chosen via the API; on a fresh start we default to
    the first model the provider(s) advertise. Returns '' if none can be listed, in
    which case AI match stays disabled until the user selects a model."""
    try:
        models = _available_models_provider.list_models()
    except Exception:  # noqa: BLE001 - never let model discovery block startup
        _logger.warning("Could not list available models at startup; no model selected", exc_info=True)
        return ""
    return models[0].model if models else ""


_initial_model = _pick_initial_model()
_disable_tracing(_initial_model)

_ai_scoring_context = AiScoringContext(
    repository=_selected_model_repository,
    build_use_case=_build_ai_use_case,
    configure_sdk=_disable_tracing,
    default_model=_initial_model,
)


def _ai_use_case_for_request(user: User = Depends(get_current_user)) -> MatchOffersWithAiUseCase:
    """Resolve the AI match use case for the calling user's selected model (per-user)."""
    return _ai_scoring_context.use_case_for(user.id)


calculate_salary_use_case = CalculateNetSalaryUseCase(SalaryCalculator())
get_model_usage_summary_use_case_instance = GetModelUsageSummaryUseCase(
    model_usage_repository, HardcodedModelLimitsRegistry()
)

app = FastAPI(title="Job Offer Matcher")
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
app.dependency_overrides[get_user_repository] = lambda: _user_repository
app.dependency_overrides[get_token_service] = lambda: _token_service
app.dependency_overrides[get_cookie_settings] = lambda: _cookie_settings
app.dependency_overrides[get_save_profile_use_case] = lambda: save_profile_use_case
app.dependency_overrides[get_profile_use_case] = lambda: get_user_profile_use_case
app.dependency_overrides[get_match_offers_use_case] = lambda: match_offers_use_case
app.dependency_overrides[get_match_offers_ai_use_case] = _ai_use_case_for_request
app.dependency_overrides[get_ai_scoring_context] = lambda: _ai_scoring_context
app.dependency_overrides[get_list_available_models_use_case] = lambda: ListAvailableModelsUseCase(_available_models_provider)
app.dependency_overrides[get_count_offers_use_case] = lambda: count_offers_use_case
app.dependency_overrides[get_list_offers_use_case] = lambda: list_offers_use_case
app.dependency_overrides[get_calculate_salary_use_case] = lambda: calculate_salary_use_case
app.dependency_overrides[get_model_usage_summary_use_case] = lambda: get_model_usage_summary_use_case_instance
app.dependency_overrides[get_budget_service] = lambda: _budget_service


def main() -> None:
    import uvicorn

    if WORKERS > 1:
        # Multiple workers require an import string so uvicorn can spawn processes.
        uvicorn.run("main:app", host=HOST, port=PORT, workers=WORKERS)
    else:
        uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
