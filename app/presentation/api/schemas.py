from __future__ import annotations

from pydantic import BaseModel, Field

from app.application.ports import ModelUsageWithLimits
from app.domain.entities import Experience, Offer, Project, Salary, Skill, UserProfile
from app.domain.matching import MatchCriteria, MatchedOffer, MatchSortBy, SortOrder
from app.domain.salary_calculator import ContractType, NetSalaryBreakdown, net_monthly_take_home


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
    offers_limit: int | None = None
    location: str | None = None
    min_salary: float | None = None
    include_expired: bool = False
    level: list[str] = []
    sort_by: MatchSortBy = "score"
    sort_order: SortOrder = "desc"

    def to_criteria(self) -> MatchCriteria:
        return MatchCriteria(
            candidate=self.candidate.to_domain(),
            min_score=self.min_score,
            location=self.location,
            min_salary=self.min_salary,
            include_expired=self.include_expired,
            level=self.level,
        )


class MatchAiRequestSchema(MatchRequestSchema):
    offers_to_score: int = Field(20, ge=1, le=50)
    ai_min_score: float = 0.0


class OffersCountSchema(BaseModel):
    total: int


class SalaryCalculationRequestSchema(BaseModel):
    contract_type: ContractType
    gross_monthly: float = Field(gt=0)
    business_costs: float = 0.0
    include_ppk: bool = False
    include_voluntary_sickness: bool = False


class SalaryCalculationResponseSchema(BaseModel):
    gross: float
    social_security: float
    health_insurance: float
    income_tax: float
    business_costs: float
    ppk: float
    take_home: float

    @classmethod
    def from_domain(cls, breakdown: NetSalaryBreakdown) -> "SalaryCalculationResponseSchema":
        return cls(
            gross=round(breakdown.gross, 2),
            social_security=round(breakdown.social_security, 2),
            health_insurance=round(breakdown.health_insurance, 2),
            income_tax=round(breakdown.income_tax, 2),
            business_costs=round(breakdown.business_costs, 2),
            ppk=round(breakdown.ppk, 2),
            take_home=round(breakdown.take_home, 2),
        )


class SalarySchema(BaseModel):
    contract_type: str
    min: float | None
    max: float | None
    currency: str
    period: str
    net_monthly: float | None

    @classmethod
    def from_domain(cls, salary: Salary) -> "SalarySchema":
        return cls(
            contract_type=salary.contract_type,
            min=salary.min_amount,
            max=salary.max_amount,
            currency=salary.currency,
            period=salary.period,
            net_monthly=net_monthly_take_home(salary),
        )


class OfferSchema(BaseModel):
    link: str
    title: str
    company: str
    locations: list[str]
    salaries: list[SalarySchema]
    tech_stack: list[str]
    tech_stack_nice_to_have: list[str]
    expired: bool
    expires: str | None
    levels: list[str]
    published: str | None

    @classmethod
    def from_domain(cls, offer: Offer) -> "OfferSchema":
        return cls(
            link=offer.link,
            title=offer.title,
            company=offer.company,
            locations=offer.locations,
            salaries=[SalarySchema.from_domain(salary) for salary in offer.salaries],
            tech_stack=offer.tech_stack,
            tech_stack_nice_to_have=offer.tech_stack_nice_to_have,
            expired=offer.expired,
            expires=offer.expires,
            levels=offer.levels,
            published=offer.published,
        )


class OffersPageSchema(BaseModel):
    offers: list[OfferSchema]
    total: int
    limit: int
    offset: int


class MatchedOfferSchema(BaseModel):
    link: str
    title: str
    company: str
    score: float
    matched_skills: list[str]
    locations: list[str]
    salaries: list[SalarySchema]
    expired: bool
    expires: str | None
    levels: list[str]
    published: str | None

    @classmethod
    def from_domain(cls, matched: MatchedOffer) -> "MatchedOfferSchema":
        return cls(
            link=matched.offer.link,
            title=matched.offer.title,
            company=matched.offer.company,
            score=matched.score,
            matched_skills=sorted(matched.matched_skills),
            locations=matched.offer.locations,
            salaries=[SalarySchema.from_domain(salary) for salary in matched.offer.salaries],
            expired=matched.offer.expired,
            expires=matched.offer.expires,
            levels=matched.offer.levels,
            published=matched.offer.published,
        )


class AiUsageSchema(BaseModel):
    input_tokens: int
    output_tokens: int


class AiMatchResponseSchema(BaseModel):
    matches: list[MatchedOfferSchema]
    usage: AiUsageSchema


class CurrentModelSchema(BaseModel):
    model: str
    company: str


class ModelLimitsSchema(BaseModel):
    rpm: int
    tpm: int
    rpd: int


class ModelUsageSummaryItemSchema(BaseModel):
    company: str
    model: str
    input_tokens: int
    output_tokens: int
    limits: ModelLimitsSchema | None

    @classmethod
    def from_domain(cls, item: "ModelUsageWithLimits") -> "ModelUsageSummaryItemSchema":
        return cls(
            company=item.company,
            model=item.model,
            input_tokens=item.input_tokens,
            output_tokens=item.output_tokens,
            limits=ModelLimitsSchema(rpm=item.limits.rpm, tpm=item.limits.tpm, rpd=item.limits.rpd)
            if item.limits else None,
        )
