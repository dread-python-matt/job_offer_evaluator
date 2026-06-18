from fastapi import APIRouter, Depends, HTTPException

from app.application.use_cases import (
    GetUserProfileUseCase,
    MatchOffersUseCase,
    SaveUserProfileUseCase,
)
from app.presentation.api.schemas import (
    MatchedOfferSchema,
    MatchRequestSchema,
    UserProfileSchema,
)

router = APIRouter()


def get_save_profile_use_case() -> SaveUserProfileUseCase:
    raise NotImplementedError("override with a configured use case")


def get_profile_use_case() -> GetUserProfileUseCase:
    raise NotImplementedError("override with a configured use case")


def get_match_offers_use_case() -> MatchOffersUseCase:
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


@router.post("/offers/match", response_model=list[MatchedOfferSchema])
def match_offers(
    match_request: MatchRequestSchema,
    use_case: MatchOffersUseCase = Depends(get_match_offers_use_case),
) -> list[MatchedOfferSchema]:
    matches = use_case.execute(
        candidate=match_request.candidate.to_domain(),
        offers_limit=match_request.offers_limit,
        min_score=match_request.min_score,
    )
    return [MatchedOfferSchema.from_domain(match) for match in matches]
