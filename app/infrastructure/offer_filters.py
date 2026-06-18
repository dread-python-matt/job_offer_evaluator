import re

from app.domain.entities import Offer, UserProfile
from app.domain.matching import MatchCriteria, OfferFilter


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
        if criteria.location is None:
            return True
        wanted = criteria.location.casefold()
        return any(wanted in location.casefold() for location in offer.locations)


class SalaryFilter(OfferFilter):
    """Passes when no minimum salary was requested, or the offer's parsed salary range
    meets it. `salary_range` is free text scraped from various job portals (e.g.
    "18000 - 22500 PLN/month", "120 - 140 PLN/hour", "B2B: 5600 - 8800 PLN/month;
    ZLECENIE: 6000 - 8000 PLN/month"). We take the upper bound of each ';'-separated
    contract-type segment, normalize hourly/daily rates to a monthly-equivalent, and use
    the best (highest) segment as the offer's representative monthly salary. Offers with
    missing or unparseable salary data are excluded when a minimum is requested, since we
    can't confirm they meet it."""

    _HOURS_PER_MONTH = 168
    _DAYS_PER_MONTH = 21

    _RANGE_RE = re.compile(
        r"(?P<low>\d+(?:\.\d+)?)\s*-\s*(?P<high>\d+(?:\.\d+)?)\s*PLN\s*/\s*(?P<period>month|hour|day)",
        re.IGNORECASE,
    )
    _SINGLE_RE = re.compile(
        r"(?P<amount>\d+(?:\.\d+)?)\s*PLN(?:\s*/\s*(?P<period>month|hour|day))?",
        re.IGNORECASE,
    )

    def passes(self, offer: Offer, criteria: MatchCriteria) -> bool:
        if criteria.min_salary is None:
            return True
        monthly_salary = self._best_monthly_salary(offer.salary_range)
        return monthly_salary is not None and monthly_salary >= criteria.min_salary

    def _best_monthly_salary(self, salary_range: str | None) -> float | None:
        if not salary_range:
            return None

        best: float | None = None
        for segment in salary_range.split(";"):
            value = self._parse_segment(segment)
            if value is not None and (best is None or value > best):
                best = value
        return best

    def _parse_segment(self, segment: str) -> float | None:
        range_match = self._RANGE_RE.search(segment)
        if range_match:
            return self._to_monthly(float(range_match["high"]), range_match["period"])

        single_match = self._SINGLE_RE.search(segment)
        if single_match:
            return self._to_monthly(float(single_match["amount"]), single_match["period"] or "month")

        return None

    def _to_monthly(self, amount: float, period: str) -> float:
        period = period.lower()
        if period == "hour":
            return amount * self._HOURS_PER_MONTH
        if period == "day":
            return amount * self._DAYS_PER_MONTH
        return amount
