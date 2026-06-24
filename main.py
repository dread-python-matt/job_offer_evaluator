import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.ai_scoring_context import AiScoringContext
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
    CORS_ORIGINS,
    DATABASE_URL,
    DEFAULT_BUDGET_USD,
    GEMINI_API_KEY,
    LLM_DEBUG,
    LLM_PROVIDER,
    OPENAI_ADMIN_KEY,
    OPENAI_API_KEY,
    USER_PROFILE_PATH,
)
from app.domain.filters import FilterChain
from app.domain.salary_calculator import SalaryCalculator
from app.infrastructure.composite_model_usage_tracker import CompositeModelUsageTracker
from app.infrastructure.composite_available_models_provider import CompositeAvailableModelsProvider
from app.infrastructure.gemini_available_models_provider import GeminiAvailableModelsProvider
from app.infrastructure.gemini_client import configure_gemini
from app.infrastructure.llm_logging import configure_llm_logging
from app.infrastructure.llm_provider_factory import build_llm_provider_factory
from app.infrastructure.llm_scoring_strategy import LLMScoringStrategy
from app.infrastructure.llm_utils import company_from_model
from app.infrastructure.openai_available_models_provider import OpenAIAvailableModelsProvider
from app.infrastructure.openai_client import configure_openai
from app.infrastructure.markdown_profile_repository import MarkdownUserProfileRepository
from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry
from app.infrastructure.offer_filters import (
    ExpiredFilter,
    LevelFilter,
    LocationFilter,
    SalaryFilter,
    SkillFilter,
)
from app.infrastructure.persisting_model_usage_tracker import PersistingModelUsageTracker
from app.infrastructure.postgres_budget_repository import PostgresBudgetRepository
from app.infrastructure.postgres_model_usage_repository import PostgresModelUsageRepository
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.scoring_strategies import SkillBasedScorer
from app.infrastructure.translation_agents import build_polish_to_english_agent
from app.presentation.api.routes import (
    get_ai_scoring_context,
    get_calculate_salary_use_case,
    get_budget_service,
    get_count_offers_use_case,
    get_current_model,
    get_list_available_models_use_case,
    get_list_offers_use_case,
    get_match_offers_ai_use_case,
    get_match_offers_use_case,
    get_model_usage_summary_use_case,
    get_profile_use_case,
    get_save_profile_use_case,
    router,
)
from app.presentation.api.schemas import CurrentModelSchema

_logger = logging.getLogger(__name__)

configure_llm_logging(LLM_DEBUG)

# LLM_PROVIDER still selects org-level usage/cost wiring; the scoring model itself
# is chosen by the user via the API (and the SDK is reconfigured per model below).
_llm_factory = build_llm_provider_factory(
    LLM_PROVIDER, OPENAI_API_KEY, OPENAI_ADMIN_KEY, GEMINI_API_KEY
)

profile_repository = MarkdownUserProfileRepository(USER_PROFILE_PATH)
offer_repository = PostgresOfferRepository(DATABASE_URL)
filter_chain = FilterChain(
    [SkillFilter(), LocationFilter(), SalaryFilter(), ExpiredFilter(), LevelFilter()]
)
model_usage_repository = PostgresModelUsageRepository(DATABASE_URL)

save_profile_use_case = SaveUserProfileUseCase(profile_repository)
get_user_profile_use_case = GetUserProfileUseCase(profile_repository)
count_offers_use_case = CountOffersUseCase(offer_repository)
list_offers_use_case = ListOffersUseCase(offer_repository)
match_offers_use_case = MatchOffersUseCase(offer_repository, SkillBasedScorer(), filter_chain)
_in_memory_tracker = InMemoryModelUsageTracker()
_persisting_tracker = PersistingModelUsageTracker(model_usage_repository)
_composite_tracker = CompositeModelUsageTracker([_in_memory_tracker, _persisting_tracker])


_budget_repository = PostgresBudgetRepository(DATABASE_URL, default_limit_usd=DEFAULT_BUDGET_USD)
_budget_service = BudgetService(_budget_repository, _llm_factory.build_spend_provider())


def _configure_sdk_for_model(model: str) -> None:
    company = company_from_model(model)
    if company == "Google":
        configure_gemini(GEMINI_API_KEY)
    elif company == "OpenAI":
        configure_openai(OPENAI_API_KEY)


def _build_ai_use_case(model: str) -> MatchOffersWithAiUseCase:
    return MatchOffersWithAiUseCase(
        offer_repository,
        filter_chain,
        SkillBasedScorer(),
        LLMScoringStrategy.create(
            model=model,
            translator_agent=build_polish_to_english_agent(model=model),
            usage_tracker=_composite_tracker,
        ),
        usage_tracker=_in_memory_tracker,
        budget=_budget_service,
        max_concurrency=AI_MATCH_CONCURRENCY,
    )


_available_models_provider = CompositeAvailableModelsProvider([
    provider
    for provider, key in [
        (GeminiAvailableModelsProvider(GEMINI_API_KEY), GEMINI_API_KEY),
        (OpenAIAvailableModelsProvider(OPENAI_API_KEY), OPENAI_API_KEY),
    ]
    if key
])


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
_configure_sdk_for_model(_initial_model)

_ai_scoring_context = AiScoringContext(
    initial_model=_initial_model,
    initial_use_case=_build_ai_use_case(_initial_model),
    build_use_case=_build_ai_use_case,
    configure_sdk=_configure_sdk_for_model,
)
calculate_salary_use_case = CalculateNetSalaryUseCase(SalaryCalculator())
_external_usage_provider = _llm_factory.build_external_usage_provider()
get_model_usage_summary_use_case_instance = GetModelUsageSummaryUseCase(
    model_usage_repository, HardcodedModelLimitsRegistry(), _external_usage_provider
)

app = FastAPI(title="Job Offer Matcher")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.dependency_overrides[get_save_profile_use_case] = lambda: save_profile_use_case
app.dependency_overrides[get_profile_use_case] = lambda: get_user_profile_use_case
app.dependency_overrides[get_match_offers_use_case] = lambda: match_offers_use_case
app.dependency_overrides[get_match_offers_ai_use_case] = lambda: _ai_scoring_context.use_case
app.dependency_overrides[get_ai_scoring_context] = lambda: _ai_scoring_context
app.dependency_overrides[get_list_available_models_use_case] = lambda: ListAvailableModelsUseCase(_available_models_provider)
app.dependency_overrides[get_count_offers_use_case] = lambda: count_offers_use_case
app.dependency_overrides[get_list_offers_use_case] = lambda: list_offers_use_case
app.dependency_overrides[get_calculate_salary_use_case] = lambda: calculate_salary_use_case
app.dependency_overrides[get_model_usage_summary_use_case] = lambda: get_model_usage_summary_use_case_instance
app.dependency_overrides[get_budget_service] = lambda: _budget_service
app.dependency_overrides[get_current_model] = lambda: CurrentModelSchema(
    model=_ai_scoring_context.active_model,
    company=company_from_model(_ai_scoring_context.active_model),
)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
