from app.domain.entities import UserProfile

# Evidence-aware weighting. Two signals decide a matched skill's weight: the candidate's
# self-rating (1-5) and whether the skill is *evidenced* — used in a real project/experience.
# Evidence is the more trustworthy signal (juniors over-claim), so it dominates:
#   - EVIDENCE_MULTIPLIER doubles the weight of an evidenced skill, so an evidenced skill always
#     outweighs the same self-rating without evidence.
#   - EVIDENCED_BASELINE gives a skill that is evidenced but left *unrated* a solid weight,
#     rather than 0 — previously such a skill contributed nothing, which is exactly backwards.
# A skill that is neither rated nor evidenced contributes nothing. Tunable here so scoring can
# be recalibrated without touching call sites.
EVIDENCE_MULTIPLIER = 2.0
EVIDENCED_BASELINE = (
    0.8  # equivalent to a self-rating of 4/5 for a skill shown by real work
)


def practiced_skills(candidate: UserProfile) -> set[str]:
    result: set[str] = set()
    for project in candidate.projects:
        result.update(tech.lower() for tech in project.tech_stack)
    for experience in candidate.experience:
        result.update(tech.lower() for tech in experience.tech_stack)
    return result


def _skill_weight(rating: int | None, practiced: bool) -> float:
    if rating is None and not practiced:
        return 0.0
    base = rating / 5 if rating is not None else EVIDENCED_BASELINE
    if practiced:
        base *= EVIDENCE_MULTIPLIER
    return base


def weighted_skill_ratio(candidate: UserProfile, required_skills: list[str]) -> float:
    if not required_skills:
        return 0.0
    ratings = {skill.name.lower(): skill.rating for skill in candidate.skills}
    candidate_practiced = practiced_skills(candidate)
    total = sum(
        _skill_weight(ratings.get(skill.lower()), skill.lower() in candidate_practiced)
        for skill in required_skills
    )
    return total / len(required_skills)
