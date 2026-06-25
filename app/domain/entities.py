from dataclasses import dataclass, field
from enum import Enum


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


class B2BTaxForm(str, Enum):
    """How a B2B (JDG) contractor is taxed. IT defaults to ryczałt 12%."""

    RYCZALT_12 = "ryczalt_12"
    RYCZALT_8_5 = "ryczalt_8_5"
    LINIOWY = "liniowy"
    SKALA = "skala"


class ZusScheme(str, Enum):
    """A B2B contractor's social-insurance basis. Defaults to the standard "duży ZUS"."""

    DUZY_ZUS = "duzy_zus"
    PREFERENTIAL = "preferential"
    ULGA_NA_START = "ulga_na_start"


@dataclass(frozen=True)
class TaxSituation:
    """Optional personal tax attributes that refine a net-salary calculation. All default
    to the baseline assumption (over 26, not a student, PIT-2 filed, B2B on ryczałt 12% +
    duży ZUS), so an absent or empty situation reproduces the calculator's default behavior.

    - `under_26`: eligible for *ulga dla młodych* — income tax is waived on umowa o pracę /
      umowa zlecenie earnings up to the annual youth-relief cap (does not apply to B2B).
    - `is_student`: a student **under 26** on umowa zlecenie pays no ZUS and no health, so
      take-home equals gross (no effect on umowa o pracę or B2B).
    - `applies_tax_credit`: whether the monthly tax-reducing amount (PIT-2) is applied.
    - `b2b_tax_form` / `b2b_zus_scheme`: only consulted for B2B contracts.
    """

    under_26: bool = False
    is_student: bool = False
    applies_tax_credit: bool = True
    b2b_tax_form: B2BTaxForm = B2BTaxForm.RYCZALT_12
    b2b_zus_scheme: ZusScheme = ZusScheme.DUZY_ZUS


@dataclass(frozen=True)
class UserProfile:
    summary: str
    skills: list[Skill]
    projects: list[Project]
    experience: list[Experience]
    tax_situation: TaxSituation = TaxSituation()

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
