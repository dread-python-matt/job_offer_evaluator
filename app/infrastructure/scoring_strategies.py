from app.domain.entities import Offer, UserProfile
from app.domain.matching import Score, ScoringStrategy


class SkillOverlapScoringStrategy(ScoringStrategy):
    """Scores an offer by the fraction of its tech stack the candidate's skills cover."""

    def score(self, candidate: UserProfile, offer: Offer) -> Score:
        return Score(skills_score=self._skills_score(candidate, offer), description_score=0.0)

    @staticmethod
    def _skills_score(candidate: UserProfile, offer: Offer) -> float:
        offer_skills = offer.skill_set()
        if not offer_skills:
            return 0.0
        matched = candidate.skill_names() & offer_skills
        return len(matched) / len(offer_skills)


class WeightedSkillScoringStrategy(ScoringStrategy):
    """Weighs each matched skill by the candidate's declared rating (0-1), doubling the
    weight of skills the candidate has actually used in a project or experience entry.
    Required and nice-to-have tech stacks are scored separately, then summed."""

    def score(self, candidate: UserProfile, offer: Offer) -> Score:
        base_score = self._weighted_ratio(candidate, offer.tech_stack)
        nice_to_have_score = self._weighted_ratio(candidate, offer.tech_stack_nice_to_have)
        return Score(skills_score=base_score + nice_to_have_score, description_score=0.0)

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
