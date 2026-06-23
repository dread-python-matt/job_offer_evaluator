from app.domain.entities import Offer
from app.domain.filters import (
    MatchCriteria,
    OfferFilter,
    expired_matches,
    level_matches,
    location_matches,
    salary_meets_minimum,
)
from app.infrastructure.skill_utils import weighted_skill_ratio


class SkillFilter(OfferFilter):
    """Cheap pre-filter that approximates skill fit without running the real
    `OfferScorer`, so expensive scoring (e.g. an LLM call) can be skipped for offers
    that clearly won't meet `min_score`."""

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        base_score = weighted_skill_ratio(criteria.candidate, offer.tech_stack)
        nice_to_have_score = weighted_skill_ratio(criteria.candidate, offer.tech_stack_nice_to_have)
        return base_score + nice_to_have_score >= criteria.min_score


class LocationFilter(OfferFilter):
    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return location_matches(offer, criteria.location)


class SalaryFilter(OfferFilter):
    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return salary_meets_minimum(offer, criteria.min_salary)


class ExpiredFilter(OfferFilter):
    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return expired_matches(offer, criteria.include_expired)


class LevelFilter(OfferFilter):
    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return level_matches(offer, criteria.level)
