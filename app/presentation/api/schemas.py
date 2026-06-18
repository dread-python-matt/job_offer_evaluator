from pydantic import BaseModel

from app.domain.entities import Experience, Project, Skill, UserProfile
from app.domain.matching import MatchedOffer


class SkillSchema(BaseModel):
    name: str
    rating: int

    def to_domain(self) -> Skill:
        return Skill(name=self.name, rating=self.rating)

    @classmethod
    def from_domain(cls, skill: Skill) -> "SkillSchema":
        return cls(name=skill.name, rating=skill.rating)


class ProjectSchema(BaseModel):
    name: str
    repository_link: str
    summary: str
    date_from: str
    date_to: str
    tech_stack: list[str]

    def to_domain(self) -> Project:
        return Project(**self.model_dump())

    @classmethod
    def from_domain(cls, project: Project) -> "ProjectSchema":
        return cls(
            name=project.name,
            repository_link=project.repository_link,
            summary=project.summary,
            date_from=project.date_from,
            date_to=project.date_to,
            tech_stack=project.tech_stack,
        )


class ExperienceSchema(BaseModel):
    title: str
    company: str
    description: str
    date_from: str
    date_to: str
    tech_stack: list[str]

    def to_domain(self) -> Experience:
        return Experience(**self.model_dump())

    @classmethod
    def from_domain(cls, experience: Experience) -> "ExperienceSchema":
        return cls(
            title=experience.title,
            company=experience.company,
            description=experience.description,
            date_from=experience.date_from,
            date_to=experience.date_to,
            tech_stack=experience.tech_stack,
        )


class UserProfileSchema(BaseModel):
    summary: str
    skills: list[SkillSchema]
    projects: list[ProjectSchema]
    experience: list[ExperienceSchema]

    def to_domain(self) -> UserProfile:
        return UserProfile(
            summary=self.summary,
            skills=[skill.to_domain() for skill in self.skills],
            projects=[project.to_domain() for project in self.projects],
            experience=[experience.to_domain() for experience in self.experience],
        )

    @classmethod
    def from_domain(cls, profile: UserProfile) -> "UserProfileSchema":
        return cls(
            summary=profile.summary,
            skills=[SkillSchema.from_domain(skill) for skill in profile.skills],
            projects=[ProjectSchema.from_domain(project) for project in profile.projects],
            experience=[
                ExperienceSchema.from_domain(experience) for experience in profile.experience
            ],
        )


class MatchRequestSchema(BaseModel):
    candidate: UserProfileSchema
    min_score: float = 0.0
    offers_limit: int = 10


class MatchedOfferSchema(BaseModel):
    link: str
    title: str
    company: str
    score: float
    matched_skills: list[str]

    @classmethod
    def from_domain(cls, matched: MatchedOffer) -> "MatchedOfferSchema":
        return cls(
            link=matched.offer.link,
            title=matched.offer.title,
            company=matched.offer.company,
            score=matched.score,
            matched_skills=sorted(matched.matched_skills),
        )
