from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.use_cases import (
    GetUserProfileUseCase,
    MatchOffersUseCase,
    SaveUserProfileUseCase,
)
from app.config import DATABASE_URL, USER_PROFILE_PATH
from app.infrastructure.markdown_profile_repository import MarkdownUserProfileRepository
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.scoring_strategies import WeightedSkillScoringStrategy
from app.presentation.api.routes import (
    get_match_offers_use_case,
    get_profile_use_case,
    get_save_profile_use_case,
    router,
)

profile_repository = MarkdownUserProfileRepository(USER_PROFILE_PATH)
offer_repository = PostgresOfferRepository(DATABASE_URL)

save_profile_use_case = SaveUserProfileUseCase(profile_repository)
get_user_profile_use_case = GetUserProfileUseCase(profile_repository)
match_offers_use_case = MatchOffersUseCase(offer_repository, WeightedSkillScoringStrategy())

app = FastAPI(title="Job Offer Matcher")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.dependency_overrides[get_save_profile_use_case] = lambda: save_profile_use_case
app.dependency_overrides[get_profile_use_case] = lambda: get_user_profile_use_case
app.dependency_overrides[get_match_offers_use_case] = lambda: match_offers_use_case


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
