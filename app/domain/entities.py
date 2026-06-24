from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skill:
    name: str
    rating: int

    def __post_init__(self) -> None:
        if not 1 <= self.rating <= 5:
            raise ValueError("Skill rating must be between 1 and 5")


@dataclass(frozen=True)
class Project:
    name: str
    repository_link: str
    summary: str
    date_from: str
    date_to: str
    tech_stack: list[str]


@dataclass(frozen=True)
class Experience:
    title: str
    company: str
    description: str
    date_from: str
    date_to: str
    tech_stack: list[str]


@dataclass(frozen=True)
class UserProfile:
    summary: str
    skills: list[Skill]
    projects: list[Project]
    experience: list[Experience]

    def skill_names(self) -> set[str]:
        return {skill.name.lower() for skill in self.skills}


@dataclass(frozen=True)
class Salary:
    contract_type: str
    min_amount: float | None
    max_amount: float | None
    currency: str
    period: str
    # Standardized NET monthly PLN figures from the scraper's normalized_salary table
    # (None when not yet computed). These are the basis for cross-contract comparison.
    net_min: float | None = None
    net_mid: float | None = None
    net_max: float | None = None


@dataclass(frozen=True)
class Offer:
    link: str
    title: str
    company: str
    tech_stack: list[str] = field(default_factory=list)
    tech_stack_nice_to_have: list[str] = field(default_factory=list)
    description: str = ""
    locations: list[str] = field(default_factory=list)
    salaries: list[Salary] = field(default_factory=list)
    expired: bool = False
    expires: str | None = None
    levels: list[str] = field(default_factory=list)
    published: str | None = None

    def skill_set(self) -> set[str]:
        return {tech.lower() for tech in (*self.tech_stack, *self.tech_stack_nice_to_have)}
