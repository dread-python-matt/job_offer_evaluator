from app.domain.entities import UserProfile


def practiced_skills(candidate: UserProfile) -> set[str]:
    result: set[str] = set()
    for project in candidate.projects:
        result.update(tech.lower() for tech in project.tech_stack)
    for experience in candidate.experience:
        result.update(tech.lower() for tech in experience.tech_stack)
    return result


def weighted_skill_ratio(candidate: UserProfile, required_skills: list[str]) -> float:
    if not required_skills:
        return 0.0
    ratings = {skill.name.lower(): skill.rating for skill in candidate.skills}
    candidate_practiced = practiced_skills(candidate)
    total = 0.0
    for skill in required_skills:
        rating = ratings.get(skill.lower())
        if rating is None:
            continue
        weight = rating / 5
        if skill.lower() in candidate_practiced:
            weight *= 2
        total += weight
    return total / len(required_skills)
