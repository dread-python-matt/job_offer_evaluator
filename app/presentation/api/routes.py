from fastapi import APIRouter, Depends, HTTPException, Query

from app.application.ports import AiScoringError
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
from app.domain.matching import OfferBrowseFilters, SortBy, SortOrder
from app.presentation.api.schemas import (
    AiMatchResponseSchema,
    AiUsageSchema,
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


def get_current_model() -> CurrentModelSchema:
    raise NotImplementedError("override with a configured model")


def get_model_usage_summary_use_case() -> GetModelUsageSummaryUseCase:
    raise NotImplementedError("override with a configured use case")


@router.post("/profile", response_model=UserProfileSchema)
def create_profile(
    payload: UserProfileSchema,
    use_case: SaveUserProfileUseCase = Depends(get_save_profile_use_case),
) -> UserProfileSchema:
    profile = payload.to_domain()
    use_case.execute(profile)
    return UserProfileSchema.from_domain(profile)


@router.get("/profile", response_model=UserProfileSchema)
def get_profile(
    use_case: GetUserProfileUseCase = Depends(get_profile_use_case),
) -> UserProfileSchema:
    profile = use_case.execute()
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
        )
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
    )
    return SalaryCalculationResponseSchema.from_domain(breakdown)


@router.get("/config/model", response_model=CurrentModelSchema)
def get_model_config(
    current_model: CurrentModelSchema = Depends(get_current_model),
) -> CurrentModelSchema:
    return current_model


@router.get("/usage/summary", response_model=list[ModelUsageSummaryItemSchema])
def get_usage_summary(
    use_case: GetModelUsageSummaryUseCase = Depends(get_model_usage_summary_use_case),
) -> list[ModelUsageSummaryItemSchema]:
    return [ModelUsageSummaryItemSchema.from_domain(item) for item in use_case.execute()]
