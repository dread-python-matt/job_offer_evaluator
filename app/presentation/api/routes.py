from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.application.ai_scoring_context import AiScoringContext
from app.application.api_key_use_cases import (
    AddApiKeyUseCase,
    DeleteApiKeyUseCase,
    ListApiKeysUseCase,
    SetApiKeyBudgetUseCase,
)
from app.application.budget_service import BudgetService
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
from app.domain.api_providers import SUPPORTED_API_PROVIDERS, company_for_provider
from app.domain.auth import User
from app.domain.errors import (
    AiScoringError,
    ApiKeyAlreadyExistsError,
    ApiKeyNotFoundError,
    BudgetExceededError,
    InvalidApiKeyError,
    UnsupportedApiProviderError,
)
from app.domain.filters import OfferBrowseFilters
from app.presentation.api.auth import get_current_user
from app.domain.sorting import SortBy, SortOrder
from app.infrastructure.llm_utils import company_from_model
from app.presentation.api.schemas import (
    AddApiKeyRequestSchema,
    AiMatchResponseSchema,
    AiUsageSchema,
    ApiKeySchema,
    ApiProviderSchema,
    AvailableModelsSchema,
    BudgetSchema,
    SetApiKeyBudgetRequestSchema,
    CompanyModelsSchema,
    CurrentModelSchema,
    MatchAiRequestSchema,
    MatchedOfferSchema,
    MatchRequestSchema,
    ModelUsageSummaryItemSchema,
    OffersCountSchema,
    OffersPageSchema,
    OfferSchema,
    SalaryCalculationRequestSchema,
    SalaryCalculationResponseSchema,
    SelectModelRequestSchema,
    SetBudgetLimitRequestSchema,
    UsageCostSchema,
    UserProfileSchema,
)

router = APIRouter()


def get_save_profile_use_case() -> SaveUserProfileUseCase:
    raise NotImplementedError("override with a configured use case")


def get_profile_use_case() -> GetUserProfileUseCase:
    raise NotImplementedError("override with a configured use case")


def get_match_offers_use_case() -> MatchOffersUseCase:
    raise NotImplementedError("override with a configured use case")


def get_match_offers_ai_use_case() -> MatchOffersWithAiUseCase:
    raise NotImplementedError("override with a configured use case")


def get_count_offers_use_case() -> CountOffersUseCase:
    raise NotImplementedError("override with a configured use case")


def get_list_offers_use_case() -> ListOffersUseCase:
    raise NotImplementedError("override with a configured use case")


def get_calculate_salary_use_case() -> CalculateNetSalaryUseCase:
    raise NotImplementedError("override with a configured use case")


def get_model_usage_summary_use_case() -> GetModelUsageSummaryUseCase:
    raise NotImplementedError("override with a configured use case")


def get_list_available_models_use_case() -> ListAvailableModelsUseCase:
    raise NotImplementedError("override with a configured use case")


def get_ai_scoring_context() -> AiScoringContext:
    raise NotImplementedError("override with a configured context")


def get_budget_service() -> BudgetService:
    raise NotImplementedError("override with a configured service")


def get_add_api_key_use_case() -> AddApiKeyUseCase:
    raise NotImplementedError("override with a configured use case")


def get_list_api_keys_use_case() -> ListApiKeysUseCase:
    raise NotImplementedError("override with a configured use case")


def get_set_api_key_budget_use_case() -> SetApiKeyBudgetUseCase:
    raise NotImplementedError("override with a configured use case")


def get_delete_api_key_use_case() -> DeleteApiKeyUseCase:
    raise NotImplementedError("override with a configured use case")


@router.post("/profile", response_model=UserProfileSchema)
def create_profile(
    payload: UserProfileSchema,
    user: User = Depends(get_current_user),
    use_case: SaveUserProfileUseCase = Depends(get_save_profile_use_case),
) -> UserProfileSchema:
    profile = payload.to_domain()
    use_case.execute(user.id, profile)
    return UserProfileSchema.from_domain(profile)


@router.get("/profile", response_model=UserProfileSchema)
def get_profile(
    user: User = Depends(get_current_user),
    use_case: GetUserProfileUseCase = Depends(get_profile_use_case),
) -> UserProfileSchema:
    profile = use_case.execute(user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile has been saved yet")
    return UserProfileSchema.from_domain(profile)


@router.get("/offers/count", response_model=OffersCountSchema)
def get_offers_count(
    use_case: CountOffersUseCase = Depends(get_count_offers_use_case),
) -> OffersCountSchema:
    return OffersCountSchema(total=use_case.execute())


@router.get("/offers", response_model=OffersPageSchema)
def list_offers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    location: str | None = None,
    min_salary: float | None = None,
    tech: list[str] = Query(default_factory=list),
    search: str | None = None,
    include_expired: bool = False,
    level: list[str] = Query(default_factory=list),
    sort_by: SortBy | None = None,
    sort_order: SortOrder = "desc",
    list_use_case: ListOffersUseCase = Depends(get_list_offers_use_case),
) -> OffersPageSchema:
    offers, total = list_use_case.execute(
        limit,
        offset,
        OfferBrowseFilters(
            location, min_salary, tech, search, include_expired, level, sort_by, sort_order
        ),
    )
    return OffersPageSchema(
        offers=[OfferSchema.from_domain(offer) for offer in offers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/offers/match", response_model=list[MatchedOfferSchema])
def match_offers(
    match_request: MatchRequestSchema,
    use_case: MatchOffersUseCase = Depends(get_match_offers_use_case),
) -> list[MatchedOfferSchema]:
    matches = use_case.execute(
        criteria=match_request.to_criteria(),
        offers_limit=match_request.offers_limit,
        sort_by=match_request.sort_by,
        sort_order=match_request.sort_order,
    )
    return [MatchedOfferSchema.from_domain(match) for match in matches]


@router.post("/offers/match/ai", response_model=AiMatchResponseSchema)
def match_offers_ai(
    match_request: MatchAiRequestSchema,
    user: User = Depends(get_current_user),
    use_case: MatchOffersWithAiUseCase = Depends(get_match_offers_ai_use_case),
) -> AiMatchResponseSchema:
    try:
        result = use_case.execute(
            criteria=match_request.to_criteria(),
            offers_to_score=match_request.offers_to_score,
            offers_limit=match_request.offers_limit,
            sort_by=match_request.sort_by,
            sort_order=match_request.sort_order,
            ai_min_score=match_request.ai_min_score,
            user_id=user.id,
        )
    except BudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except AiScoringError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AiMatchResponseSchema(
        matches=[MatchedOfferSchema.from_domain(m) for m in result.matches],
        usage=AiUsageSchema(
            input_tokens=sum(u.input_tokens for u in result.usage),
            output_tokens=sum(u.output_tokens for u in result.usage),
        ),
    )


@router.post("/salary/calculate", response_model=SalaryCalculationResponseSchema)
def calculate_salary(
    payload: SalaryCalculationRequestSchema,
    use_case: CalculateNetSalaryUseCase = Depends(get_calculate_salary_use_case),
) -> SalaryCalculationResponseSchema:
    breakdown = use_case.execute(
        contract_type=payload.contract_type,
        gross_monthly=payload.gross_monthly,
        business_costs=payload.business_costs,
        include_ppk=payload.include_ppk,
        include_voluntary_sickness=payload.include_voluntary_sickness,
        situation=payload.to_tax_situation(),
    )
    return SalaryCalculationResponseSchema.from_domain(breakdown)


@router.get("/config/model", response_model=CurrentModelSchema)
def get_model_config(
    user: User = Depends(get_current_user),
    context: AiScoringContext = Depends(get_ai_scoring_context),
) -> CurrentModelSchema:
    model = context.active_model_for(user.id)
    return CurrentModelSchema(model=model, company=company_from_model(model))


@router.get("/config/models", response_model=AvailableModelsSchema)
def get_available_models(
    user: User = Depends(get_current_user),
    use_case: ListAvailableModelsUseCase = Depends(get_list_available_models_use_case),
    context: AiScoringContext = Depends(get_ai_scoring_context),
) -> AvailableModelsSchema:
    all_models = use_case.execute()
    by_company: dict[str, list[str]] = {}
    for m in all_models:
        by_company.setdefault(m.company, []).append(m.model)
    companies = [CompanyModelsSchema(name=company, models=models) for company, models in sorted(by_company.items())]
    active_model = context.active_model_for(user.id)
    return AvailableModelsSchema(
        companies=companies,
        active=CurrentModelSchema(model=active_model, company=company_from_model(active_model)),
    )


@router.put("/config/model", response_model=CurrentModelSchema)
def select_model(
    payload: SelectModelRequestSchema,
    user: User = Depends(get_current_user),
    use_case: ListAvailableModelsUseCase = Depends(get_list_available_models_use_case),
    context: AiScoringContext = Depends(get_ai_scoring_context),
) -> CurrentModelSchema:
    available = {m.model for m in use_case.execute()}
    if payload.model not in available:
        raise HTTPException(status_code=404, detail=f"Model '{payload.model}' is not available")
    context.select_model(user.id, payload.model)
    return CurrentModelSchema(model=payload.model, company=company_from_model(payload.model))


@router.get("/usage/cost", response_model=UsageCostSchema | None)
def get_usage_cost(
    user: User = Depends(get_current_user),
    service: BudgetService = Depends(get_budget_service),
) -> UsageCostSchema | None:
    status = service.status(user.id)
    if status.used_usd is None:
        return None
    return UsageCostSchema(cost_usd=status.used_usd, limit_usd=status.limit_usd)


@router.put("/usage/limit", response_model=BudgetSchema)
def set_usage_limit(
    payload: SetBudgetLimitRequestSchema,
    user: User = Depends(get_current_user),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetSchema:
    return BudgetSchema.from_domain(service.set_limit(user.id, payload.limit_usd))


@router.post("/usage/reset", response_model=BudgetSchema)
def reset_usage(
    user: User = Depends(get_current_user),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetSchema:
    return BudgetSchema.from_domain(service.reset_usage(user.id))


@router.get("/usage/summary", response_model=list[ModelUsageSummaryItemSchema])
def get_usage_summary(
    user: User = Depends(get_current_user),
    use_case: GetModelUsageSummaryUseCase = Depends(get_model_usage_summary_use_case),
) -> list[ModelUsageSummaryItemSchema]:
    return [ModelUsageSummaryItemSchema.from_domain(item) for item in use_case.execute(user.id)]


@router.get("/api-keys/providers", response_model=list[ApiProviderSchema])
def list_api_key_providers() -> list[ApiProviderSchema]:
    """The fixed list of providers a user may register a key for (drives the picker UI)."""
    return [
        ApiProviderSchema(provider=provider, company=company_for_provider(provider))
        for provider in SUPPORTED_API_PROVIDERS
    ]


@router.get("/api-keys", response_model=list[ApiKeySchema])
def list_api_keys(
    user: User = Depends(get_current_user),
    use_case: ListApiKeysUseCase = Depends(get_list_api_keys_use_case),
) -> list[ApiKeySchema]:
    return [ApiKeySchema.from_view(view) for view in use_case.execute(user.id)]


@router.post("/api-keys", response_model=ApiKeySchema, status_code=201)
def add_api_key(
    payload: AddApiKeyRequestSchema,
    user: User = Depends(get_current_user),
    use_case: AddApiKeyUseCase = Depends(get_add_api_key_use_case),
) -> ApiKeySchema:
    try:
        view = use_case.execute(user.id, payload.api_provider, payload.key, payload.limit_usd)
    except UnsupportedApiProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InvalidApiKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ApiKeyAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiKeySchema.from_view(view)


@router.patch("/api-keys/{api_provider}", response_model=ApiKeySchema)
def set_api_key_budget(
    api_provider: str,
    payload: SetApiKeyBudgetRequestSchema,
    user: User = Depends(get_current_user),
    use_case: SetApiKeyBudgetUseCase = Depends(get_set_api_key_budget_use_case),
) -> ApiKeySchema:
    try:
        view = use_case.execute(user.id, api_provider, payload.limit_usd)
    except ApiKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiKeySchema.from_view(view)


@router.delete("/api-keys/{api_provider}", status_code=204)
def delete_api_key(
    api_provider: str,
    user: User = Depends(get_current_user),
    use_case: DeleteApiKeyUseCase = Depends(get_delete_api_key_use_case),
) -> Response:
    try:
        use_case.execute(user.id, api_provider)
    except ApiKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
