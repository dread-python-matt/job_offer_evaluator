from app.domain.entities import Offer, UserProfile
from app.domain.matching import (
    MatchCriteria,
    OfferFilter,
    expired_matches,
    level_matches,
    location_matches,
    salary_meets_minimum,
)


class SkillFilter(OfferFilter):
    """Cheap pre-filter that approximates skill fit without running the real
    `OfferScorer`, so expensive scoring (e.g. an LLM call) can be skipped for offers
    that clearly won't meet `min_score`. Intentionally duplicates the weighting logic
    rather than delegating to `SkillBasedScorer`, so the two can evolve independently."""

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        base_score = self._weighted_ratio(criteria.candidate, offer.tech_stack)
        nice_to_have_score = self._weighted_ratio(criteria.candidate, offer.tech_stack_nice_to_have)
        return base_score + nice_to_have_score >= criteria.min_score

    def _weighted_ratio(self, candidate: UserProfile, required_skills: list[str]) -> float:
        if not required_skills:
            return 0.0

        ratings = {skill.name.lower(): skill.rating for skill in candidate.skills}
        practiced_skills = self._practiced_skills(candidate)

        total = 0.0
        for skill in required_skills:
            rating = ratings.get(skill.lower())
            if rating is None:
                continue
            weight = rating / 5
            if skill.lower() in practiced_skills:
                weight *= 2
            total += weight

        return total / len(required_skills)

    @staticmethod
    def _practiced_skills(candidate: UserProfile) -> set[str]:
        practiced = set()
        for project in candidate.projects:
            practiced.update(tech.lower() for tech in project.tech_stack)
        for experience in candidate.experience:
            practiced.update(tech.lower() for tech in experience.tech_stack)
        return practiced


class LocationFilter(OfferFilter):
    """Passes when no location was requested, or the requested text appears
    (case-insensitively) in at least one of the offer's locations."""

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return location_matches(offer, criteria.location)


class SalaryFilter(OfferFilter):
    """Passes when no minimum salary was requested, or the offer's parsed salary range
    meets it (see `salary_meets_minimum`)."""

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return salary_meets_minimum(offer, criteria.min_salary)


class ExpiredFilter(OfferFilter):
    """Excludes expired offers unless the caller explicitly asked to include them."""

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return expired_matches(offer, criteria.include_expired)


class LevelFilter(OfferFilter):
    """Passes when no level was requested, or it appears (case-insensitively) among
    the offer's levels."""

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        return level_matches(offer, criteria.level)
