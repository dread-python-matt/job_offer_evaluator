from app.domain.entities import UserProfile

# Evidence-aware skill weighting. A matched skill's contribution is decided by two explicit,
# tunable features: the candidate's self-rating (1-5) and whether the skill is *evidenced* — used
# in a real project/experience. Evidence is the trustworthy signal (juniors over-claim), so it
# both amplifies and caps:
#   - EVIDENCE_MULTIPLIER doubles an evidenced skill's weight, so an evidenced skill always
#     outweighs the same self-rating without evidence.
#   - EVIDENCED_BASELINE gives a skill that is evidenced but left *unrated* a solid weight, rather
#     than 0 — previously such a skill contributed nothing, which is exactly backwards.
#   - UNEVIDENCED_SELF_RATING_CAP limits how far a bare self-claim counts: without evidence we
#     trust a rating only up to "competent" (3/5), so an un-evidenced 4-5/5 is reined in. This is
#     the main recalibration knob — raise it toward 1.0 to trust self-claims more, lower it to
#     demand evidence; 1.0 disables the cap (the pre-cap behavior).
# A skill that is neither rated nor evidenced contributes nothing. All tunable here so scoring can
# be recalibrated without touching call sites.
EVIDENCE_MULTIPLIER = 2.0
EVIDENCED_BASELINE = 0.8  # like a 4/5
UNEVIDENCED_SELF_RATING_CAP = 0.6  # like a 3/5


def practiced_skills(candidate: UserProfile) -> set[str]:
    result: set[str] = set()
    for project in candidate.projects:
        result.update(tech.lower() for tech in project.tech_stack)
    for experience in candidate.experience:
        result.update(tech.lower() for tech in experience.tech_stack)
    return result


def _skill_weight(rating: int | None, evidenced: bool) -> float:
    if rating is None and not evidenced:
        return 0.0
    base = rating / 5 if rating is not None else EVIDENCED_BASELINE
    if evidenced:
        return base * EVIDENCE_MULTIPLIER
    # Un-evidenced self-claim: trusted only up to the cap, so a high self-rating can't rival an
    # evidenced skill and serial over-claiming (rating everything 5) is blunted.
    return min(base, UNEVIDENCED_SELF_RATING_CAP)


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
