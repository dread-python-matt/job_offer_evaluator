from app.domain.entities import Offer, UserProfile
from app.domain.matching import MatchScore, OfferScorer, ScoreComponent


class SkillBasedScorer(OfferScorer):
    """Weighs each matched skill by the candidate's declared rating (0-1), doubling the
    weight of skills the candidate has actually used in a project or experience entry.
    Required and nice-to-have tech stacks are scored separately, then summed."""

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        base_score = self._weighted_ratio(candidate, offer.tech_stack)
        nice_to_have_score = self._weighted_ratio(candidate, offer.tech_stack_nice_to_have)
        skills_score = base_score + nice_to_have_score
        return MatchScore().with_component(
            ScoreComponent(name="skills", value=skills_score, weight=1.0)
        )

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
