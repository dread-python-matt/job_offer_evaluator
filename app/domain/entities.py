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
class Offer:
    link: str
    title: str
    company: str
    tech_stack: list[str] = field(default_factory=list)
    tech_stack_nice_to_have: list[str] = field(default_factory=list)
    description: str = ""
    locations: list[str] = field(default_factory=list)
    salary_range: str | None = None

    def skill_set(self) -> set[str]:
        return {tech.lower() for tech in (*self.tech_stack, *self.tech_stack_nice_to_have)}
