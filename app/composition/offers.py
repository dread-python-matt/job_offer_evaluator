"""Composition of the deterministic, non-AI use cases: the user profile, offer counting/
browsing, deterministic (skill-based) matching, and the net-salary calculator. These depend
only on the shared `Foundation`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.use_cases import (
    CalculateNetSalaryUseCase,
    CountOffersUseCase,
    GetUserProfileUseCase,
    ListOffersUseCase,
    MatchOffersUseCase,
    SaveUserProfileUseCase,
)
from app.composition.foundation import Foundation
from app.domain.salary_calculator import SalaryCalculator
from app.infrastructure.scoring_strategies import SkillBasedScorer


@dataclass(frozen=True)
class OfferUseCases:
    save_profile: SaveUserProfileUseCase
    get_profile: GetUserProfileUseCase
    count_offers: CountOffersUseCase
    list_offers: ListOffersUseCase
    match_offers: MatchOffersUseCase
    calculate_salary: CalculateNetSalaryUseCase


def build_offer_use_cases(foundation: Foundation) -> OfferUseCases:
    return OfferUseCases(
        save_profile=SaveUserProfileUseCase(foundation.profile_repository),
        get_profile=GetUserProfileUseCase(foundation.profile_repository),
        count_offers=CountOffersUseCase(foundation.offer_repository),
        list_offers=ListOffersUseCase(foundation.offer_repository),
        match_offers=MatchOffersUseCase(
            foundation.offer_repository,
            SkillBasedScorer(),
            foundation.filter_chain,
            canonicalizer=foundation.skill_canonicalizer,
        ),
        calculate_salary=CalculateNetSalaryUseCase(SalaryCalculator()),
    )
