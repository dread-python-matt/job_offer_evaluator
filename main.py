from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.ports import InMemoryModelUsageTracker
from app.application.use_cases import (
    CalculateNetSalaryUseCase,
    CountOffersUseCase,
    GetModelUsageSummaryUseCase,
    GetUserProfileUseCase,
    ListOffersUseCase,
    MatchOffersUseCase,
    MatchOffersWithAiUseCase,
    SaveUserProfileUseCase,
)
from app.config import (
    CORS_ORIGINS,
    DATABASE_URL,
    GEMINI_API_KEY,
    LLM_PROVIDER,
    OPENAI_ADMIN_KEY,
    OPENAI_API_KEY,
    SCORING_AGENT_MODEL,
    USER_PROFILE_PATH,
)
from app.domain.filters import FilterChain
from app.domain.salary_calculator import SalaryCalculator
from app.infrastructure.composite_model_usage_tracker import CompositeModelUsageTracker
from app.infrastructure.llm_provider_factory import build_llm_provider_factory
from app.infrastructure.llm_scoring_strategy import LLMScoringStrategy
from app.infrastructure.llm_utils import company_from_model
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
from app.infrastructure.postgres_model_usage_repository import PostgresModelUsageRepository
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.scoring_strategies import SkillBasedScorer
from app.infrastructure.translation_agents import build_polish_to_english_agent
from app.presentation.api.routes import (
    get_calculate_salary_use_case,
    get_count_offers_use_case,
    get_current_model,
    get_list_offers_use_case,
    get_match_offers_ai_use_case,
    get_match_offers_use_case,
    get_model_usage_summary_use_case,
    get_profile_use_case,
    get_save_profile_use_case,
    router,
)
from app.presentation.api.schemas import CurrentModelSchema

_llm_factory = build_llm_provider_factory(LLM_PROVIDER, OPENAI_API_KEY, OPENAI_ADMIN_KEY, GEMINI_API_KEY)
_llm_factory.configure_sdk()

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
match_offers_ai_use_case = MatchOffersWithAiUseCase(
    offer_repository,
    filter_chain,
    SkillBasedScorer(),
    LLMScoringStrategy.create(
        model=SCORING_AGENT_MODEL,
        translator_agent=build_polish_to_english_agent(model=SCORING_AGENT_MODEL),
        usage_tracker=_composite_tracker,
    ),
    usage_tracker=_in_memory_tracker,
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
app.dependency_overrides[get_match_offers_ai_use_case] = lambda: match_offers_ai_use_case
app.dependency_overrides[get_count_offers_use_case] = lambda: count_offers_use_case
app.dependency_overrides[get_list_offers_use_case] = lambda: list_offers_use_case
app.dependency_overrides[get_calculate_salary_use_case] = lambda: calculate_salary_use_case
app.dependency_overrides[get_model_usage_summary_use_case] = lambda: get_model_usage_summary_use_case_instance
_current_model = CurrentModelSchema(
    model=SCORING_AGENT_MODEL or "",
    company=company_from_model(SCORING_AGENT_MODEL or ""),
)
app.dependency_overrides[get_current_model] = lambda: _current_model


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
