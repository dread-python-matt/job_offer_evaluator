from app.domain.entities import Offer, UserProfile
from app.domain.scoring import MatchScore, OfferScorer, ScoreComponent
from app.infrastructure.skill_utils import weighted_skill_ratio


class SkillBasedScorer(OfferScorer):
    """Weighs each matched skill by the candidate's declared rating (0-1), doubling the
    weight of skills the candidate has actually used in a project or experience entry.
    Required and nice-to-have tech stacks are scored separately, then summed."""

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        base_score = weighted_skill_ratio(candidate, offer.tech_stack)
        nice_to_have_score = weighted_skill_ratio(candidate, offer.tech_stack_nice_to_have)
        return MatchScore().with_component(
            ScoreComponent(name="skills", value=base_score + nice_to_have_score, weight=1.0)
        )
