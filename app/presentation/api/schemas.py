from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.application.ports import ModelUsageWithLimits
from app.domain.auth import User
from app.domain.budget import BudgetStatus
from app.domain.entities import (
    B2BTaxForm,
    Experience,
    Offer,
    Project,
    Salary,
    Skill,
    TaxSituation,
    UserProfile,
    ZusScheme,
)
from app.domain.filters import MatchCriteria
from app.domain.salary_calculator import ContractType, NetSalaryBreakdown
from app.domain.scoring import AiInsight, MatchedOffer
from app.domain.sorting import MatchSortBy, SortOrder


class SkillSchema(BaseModel):
    name: str = Field(max_length=200)
    # Mirrors the domain rule (Skill enforces 1..5) so an out-of-range value is a clean 422
    # at the edge rather than a 500 from the domain constructor.
    rating: int = Field(ge=1, le=5)

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


class TaxSituationSchema(BaseModel):
    """Optional personal tax attributes that refine net-salary calculations. Defaults
    reproduce the baseline assumption (over 26, not a student, PIT-2 filed)."""

    under_26: bool = False
    is_student: bool = False
    applies_tax_credit: bool = True
    b2b_tax_form: B2BTaxForm = B2BTaxForm.RYCZALT_12
    b2b_zus_scheme: ZusScheme = ZusScheme.DUZY_ZUS

    def to_domain(self) -> TaxSituation:
        return TaxSituation(
            under_26=self.under_26,
            is_student=self.is_student,
            applies_tax_credit=self.applies_tax_credit,
            b2b_tax_form=self.b2b_tax_form,
            b2b_zus_scheme=self.b2b_zus_scheme,
        )

    @classmethod
    def from_domain(cls, situation: TaxSituation) -> "TaxSituationSchema":
        return cls(
            under_26=situation.under_26,
            is_student=situation.is_student,
            applies_tax_credit=situation.applies_tax_credit,
            b2b_tax_form=situation.b2b_tax_form,
            b2b_zus_scheme=situation.b2b_zus_scheme,
        )


class UserProfileSchema(BaseModel):
    # Caps bound the work a single match request can trigger (scoring loops + LLM prompt
    # size), so an oversized profile can't be used as a DoS amplifier.
    summary: str = Field(max_length=20_000)
    skills: list[SkillSchema] = Field(max_length=200)
    projects: list[ProjectSchema] = Field(max_length=100)
    experience: list[ExperienceSchema] = Field(max_length=100)
    tax_situation: TaxSituationSchema = Field(default_factory=TaxSituationSchema)

    def to_domain(self) -> UserProfile:
        return UserProfile(
            summary=self.summary,
            skills=[skill.to_domain() for skill in self.skills],
            projects=[project.to_domain() for project in self.projects],
            experience=[experience.to_domain() for experience in self.experience],
            tax_situation=self.tax_situation.to_domain(),
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
            tax_situation=TaxSituationSchema.from_domain(profile.tax_situation),
        )


class MatchRequestSchema(BaseModel):
    candidate: UserProfileSchema
    min_score: float = 0.0
    # Bounded so a single request can't ask the server to materialize an unbounded result set.
    offers_limit: int | None = Field(default=None, ge=1, le=200)
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
    # Optional personal tax attributes; defaults reproduce the baseline calculation.
    under_26: bool = False
    is_student: bool = False
    applies_tax_credit: bool = True
    b2b_tax_form: B2BTaxForm = B2BTaxForm.RYCZALT_12
    b2b_zus_scheme: ZusScheme = ZusScheme.DUZY_ZUS

    def to_tax_situation(self) -> TaxSituation:
        return TaxSituation(
            under_26=self.under_26,
            is_student=self.is_student,
            applies_tax_credit=self.applies_tax_credit,
            b2b_tax_form=self.b2b_tax_form,
            b2b_zus_scheme=self.b2b_zus_scheme,
        )


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
    # Standardized estimated NET monthly PLN (from the scraper's normalized_salary).
    # `net_monthly` is the midpoint (the representative figure shown by default).
    net_monthly: float | None
    net_min: float | None
    net_max: float | None

    @classmethod
    def from_domain(cls, salary: Salary) -> "SalarySchema":
        return cls(
            contract_type=salary.contract_type,
            min=salary.min_amount,
            max=salary.max_amount,
            currency=salary.currency,
            period=salary.period,
            net_monthly=salary.net_mid,
            net_min=salary.net_min,
            net_max=salary.net_max,
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


class AiInsightSchema(BaseModel):
    rate: int
    pros: list[str]
    cons: list[str]
    rate_reason: str

    @classmethod
    def from_domain(cls, insight: AiInsight) -> "AiInsightSchema":
        return cls(
            rate=insight.rate,
            pros=list(insight.pros),
            cons=list(insight.cons),
            rate_reason=insight.rate_reason,
        )


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
    ai_insight: AiInsightSchema | None = None

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
            ai_insight=(
                AiInsightSchema.from_domain(matched.ai_insight) if matched.ai_insight else None
            ),
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


class SelectModelRequestSchema(BaseModel):
    model: str


class CompanyModelsSchema(BaseModel):
    name: str
    models: list[str]


class AvailableModelsSchema(BaseModel):
    companies: list[CompanyModelsSchema]
    active: CurrentModelSchema


class UsageCostSchema(BaseModel):
    # `cost_usd` is cumulative spend since the budget tracking anchor (not daily); the
    # field name is kept for the existing frontend contract.
    cost_usd: float
    limit_usd: float


class BudgetSchema(BaseModel):
    limit_usd: float
    used_usd: float | None
    tracking_since: datetime

    @classmethod
    def from_domain(cls, status: BudgetStatus) -> "BudgetSchema":
        return cls(
            limit_usd=status.limit_usd,
            used_usd=status.used_usd,
            tracking_since=status.tracking_since,
        )


class SetBudgetLimitRequestSchema(BaseModel):
    limit_usd: float = Field(ge=0)


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


# Minimum is enforced server-side regardless of any client-side validation.
_MIN_PASSWORD_LENGTH = 10


class RegisterRequestSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)
    # Retyped password; must match `password`. Enforced server-side regardless of any
    # client-side check so the API never relies on the form alone.
    confirm_password: str

    @model_validator(mode="after")
    def _passwords_match(self) -> RegisterRequestSchema:
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequestSchema(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequestSchema(BaseModel):
    token: str


class ChangePasswordRequestSchema(BaseModel):
    current_password: str
    new_password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)


class ForgotPasswordRequestSchema(BaseModel):
    email: EmailStr


class ResetPasswordRequestSchema(BaseModel):
    token: str
    new_password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)
    # Retyped password; must match `new_password`. Enforced server-side too.
    confirm_password: str

    @model_validator(mode="after")
    def _passwords_match(self) -> ResetPasswordRequestSchema:
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class PasswordResetRequestedSchema(BaseModel):
    """Returned by forgot-password. Deliberately the same whether or not the email is
    registered, so the endpoint can't be used to discover accounts (enumeration-resistant)."""

    message: str = "If that email is registered, a reset link has been sent."


class RegistrationPendingSchema(BaseModel):
    """Returned by registration: the account exists but is unverified, and a confirmation
    email has been sent. No session is issued until the link is followed."""

    email: str
    message: str = "Check your email to confirm your account."


class UserResponseSchema(BaseModel):
    id: str
    email: str

    @classmethod
    def from_domain(cls, user: User) -> "UserResponseSchema":
        return cls(id=user.id, email=user.email)
