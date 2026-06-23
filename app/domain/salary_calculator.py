"""Net ("take-home") monthly PLN salary calculator for Polish 2026 tax/ZUS rules.

Every user is assumed to be over 26 (no "PIT dla młodych" youth exemption) and a
PIT-2 filer with the standard tax-free amount applied monthly. Simplifying
assumptions, documented per contract type below, trade a few edge cases for a
calculator that needs only a single month's gross amount as input.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.domain.entities import Offer, Salary

_HOURS_PER_MONTH = 168
_DAYS_PER_MONTH = 21
_MONTHS_PER_YEAR = 12

_MONTHLY_FACTOR_BY_PERIOD = {
    "month": 1.0,
    "hour": float(_HOURS_PER_MONTH),
    "day": float(_DAYS_PER_MONTH),
    "year": 1.0 / _MONTHS_PER_YEAR,
}


def monthly_gross_amount(salary: Salary) -> float | None:
    """A salary entry's amount normalized to a monthly gross figure, or `None` if its
    `period` can't be normalized (e.g. unknown/blank)."""
    amount = salary.max_amount if salary.max_amount is not None else salary.min_amount
    if amount is None:
        return None
    factor = _MONTHLY_FACTOR_BY_PERIOD.get(salary.period)
    if factor is None:
        return None
    return amount * factor


def representative_monthly_salary(offer: Offer) -> float | None:
    """The offer's best (highest) salary entry normalized to a monthly amount, or
    `None` if it has no salary entries whose period can be normalized."""
    monthly_amounts = [
        amount
        for salary in offer.salaries
        if (amount := monthly_gross_amount(salary)) is not None
    ]
    return max(monthly_amounts) if monthly_amounts else None

# -- Employee-side ZUS rates (employment & civil contracts; the employer/payer
# finances the remaining share, which doesn't reduce the worker's own take-home). --
EMPLOYEE_PENSION_RATE = 0.0976
EMPLOYEE_DISABILITY_RATE = 0.015
EMPLOYEE_SICKNESS_RATE = 0.0245  # mandatory for employment, voluntary for civil/B2B

EMPLOYMENT_SOCIAL_SECURITY_RATE = (
    EMPLOYEE_PENSION_RATE + EMPLOYEE_DISABILITY_RATE + EMPLOYEE_SICKNESS_RATE
)
CIVIL_CONTRACT_BASE_SOCIAL_SECURITY_RATE = EMPLOYEE_PENSION_RATE + EMPLOYEE_DISABILITY_RATE

HEALTH_INSURANCE_RATE = 0.09

# -- PIT (skala podatkowa: employment & civil contracts). The 120,000 PLN/year
# bracket threshold is divided by 12 here, approximating a worker with constant
# monthly income year-round rather than tracking cumulative annual withholding. --
TAX_CREDIT_MONTHLY = 300.0  # kwota zmniejszająca podatek (30,000 PLN/year tax-free amount)
FIRST_BRACKET_RATE = 0.12
FIRST_BRACKET_MONTHLY_LIMIT = 120_000.0 / 12
SECOND_BRACKET_RATE = 0.32

EMPLOYMENT_KUP_MONTHLY = 250.0  # standard koszty uzyskania przychodu
CIVIL_CONTRACT_KUP_RATE = 0.20  # lump-sum koszty uzyskania przychodu

PPK_EMPLOYEE_RATE = 0.02

# -- B2B, assumed on ryczałt ewidencjonowany at the 12% IT-services rate and
# "duży ZUS" (standard, non-preferential) social security — the only ZUS scheme
# with no time limit, so the most representative baseline for an established
# contractor. Self-employed people pay the full (not split) social security rate. --
SELF_EMPLOYED_PENSION_RATE = 0.1952
SELF_EMPLOYED_DISABILITY_RATE = 0.08
SELF_EMPLOYED_SICKNESS_RATE = 0.0245  # voluntary
SELF_EMPLOYED_LABOR_FUND_RATE = 0.0245
SELF_EMPLOYED_ACCIDENT_RATE = 0.0167  # default rate for businesses with <=9 insured people

B2B_FULL_ZUS_BASE_2026 = 5652.60  # 60% of the 2026 forecasted average wage
B2B_MANDATORY_SOCIAL_SECURITY_RATE = (
    SELF_EMPLOYED_PENSION_RATE
    + SELF_EMPLOYED_DISABILITY_RATE
    + SELF_EMPLOYED_LABOR_FUND_RATE
    + SELF_EMPLOYED_ACCIDENT_RATE
)

B2B_RYCZALT_TAX_RATE = 0.12
B2B_RYCZALT_HEALTH_DEDUCTIBLE_SHARE = 0.5  # 50% of paid health insurance deducts from revenue

# Ryczałt health insurance is tiered by annual revenue, based on 60%/100%/180% of the
# 2026 average enterprise wage (9,228.64 PLN) at the flat 9% health rate.
B2B_RYCZALT_REVENUE_TIER_1_ANNUAL_LIMIT = 60_000.0
B2B_RYCZALT_REVENUE_TIER_2_ANNUAL_LIMIT = 300_000.0
B2B_RYCZALT_HEALTH_TIER_1_MONTHLY = 498.35
B2B_RYCZALT_HEALTH_TIER_2_MONTHLY = 830.58
B2B_RYCZALT_HEALTH_TIER_3_MONTHLY = 1495.04


class ContractType(Enum):
    B2B = "b2b"
    EMPLOYMENT = "employment"
    CIVIL = "civil"


_CONTRACT_TYPE_LABELS = {
    "b2b": ContractType.B2B,
    "permanent": ContractType.EMPLOYMENT,
    "zlecenie": ContractType.CIVIL,
}


def contract_type_from_label(label: str) -> ContractType | None:
    """Maps a scraped `Salary.contract_type` label to a `ContractType`, or `None` if
    it isn't one we know how to calculate net pay for."""
    return _CONTRACT_TYPE_LABELS.get(label.casefold())


@dataclass(frozen=True)
class NetSalaryBreakdown:
    gross: float
    social_security: float
    health_insurance: float
    income_tax: float
    business_costs: float = 0.0
    ppk: float = 0.0

    @property
    def take_home(self) -> float:
        return (
            self.gross
            - self.business_costs
            - self.social_security
            - self.health_insurance
            - self.income_tax
            - self.ppk
        )


def _progressive_tax(taxable_income_monthly: float) -> float:
    if taxable_income_monthly <= FIRST_BRACKET_MONTHLY_LIMIT:
        tax = taxable_income_monthly * FIRST_BRACKET_RATE
    else:
        tax = FIRST_BRACKET_MONTHLY_LIMIT * FIRST_BRACKET_RATE + (
            taxable_income_monthly - FIRST_BRACKET_MONTHLY_LIMIT
        ) * SECOND_BRACKET_RATE
    return max(0.0, tax - TAX_CREDIT_MONTHLY)


class _SalaryStrategy(ABC):
    @abstractmethod
    def calculate(
        self,
        gross: float,
        *,
        business_costs: float = 0.0,
        include_ppk: bool = False,
        include_voluntary_sickness: bool = False,
    ) -> NetSalaryBreakdown: ...


class _EmploymentStrategy(_SalaryStrategy):
    def calculate(self, gross: float, *, include_ppk: bool = False, **_: object) -> NetSalaryBreakdown:
        social_security = gross * EMPLOYMENT_SOCIAL_SECURITY_RATE
        health_insurance = (gross - social_security) * HEALTH_INSURANCE_RATE
        taxable_income = max(0.0, gross - social_security - EMPLOYMENT_KUP_MONTHLY)
        income_tax = _progressive_tax(taxable_income)
        ppk = gross * PPK_EMPLOYEE_RATE if include_ppk else 0.0
        return NetSalaryBreakdown(
            gross=gross,
            social_security=social_security,
            health_insurance=health_insurance,
            income_tax=income_tax,
            ppk=ppk,
        )


class _CivilContractStrategy(_SalaryStrategy):
    def calculate(self, gross: float, *, include_voluntary_sickness: bool = False, **_: object) -> NetSalaryBreakdown:
        rate = CIVIL_CONTRACT_BASE_SOCIAL_SECURITY_RATE
        if include_voluntary_sickness:
            rate += EMPLOYEE_SICKNESS_RATE
        social_security = gross * rate
        health_insurance = (gross - social_security) * HEALTH_INSURANCE_RATE
        kup = (gross - social_security) * CIVIL_CONTRACT_KUP_RATE
        taxable_income = max(0.0, gross - social_security - kup)
        income_tax = _progressive_tax(taxable_income)
        return NetSalaryBreakdown(
            gross=gross,
            social_security=social_security,
            health_insurance=health_insurance,
            income_tax=income_tax,
        )


class _B2BStrategy(_SalaryStrategy):
    def calculate(
        self,
        gross: float,
        *,
        business_costs: float = 0.0,
        include_voluntary_sickness: bool = False,
        **_: object,
    ) -> NetSalaryBreakdown:
        rate = B2B_MANDATORY_SOCIAL_SECURITY_RATE
        if include_voluntary_sickness:
            rate += SELF_EMPLOYED_SICKNESS_RATE
        social_security = B2B_FULL_ZUS_BASE_2026 * rate

        annual_revenue_estimate = gross * 12
        if annual_revenue_estimate <= B2B_RYCZALT_REVENUE_TIER_1_ANNUAL_LIMIT:
            health_insurance = B2B_RYCZALT_HEALTH_TIER_1_MONTHLY
        elif annual_revenue_estimate <= B2B_RYCZALT_REVENUE_TIER_2_ANNUAL_LIMIT:
            health_insurance = B2B_RYCZALT_HEALTH_TIER_2_MONTHLY
        else:
            health_insurance = B2B_RYCZALT_HEALTH_TIER_3_MONTHLY

        taxable_revenue = max(
            0.0,
            gross - social_security - health_insurance * B2B_RYCZALT_HEALTH_DEDUCTIBLE_SHARE,
        )
        income_tax = taxable_revenue * B2B_RYCZALT_TAX_RATE
        return NetSalaryBreakdown(
            gross=gross,
            social_security=social_security,
            health_insurance=health_insurance,
            income_tax=income_tax,
            business_costs=business_costs,
        )


_STRATEGIES: dict[ContractType, _SalaryStrategy] = {
    ContractType.EMPLOYMENT: _EmploymentStrategy(),
    ContractType.CIVIL: _CivilContractStrategy(),
    ContractType.B2B: _B2BStrategy(),
}


class SalaryCalculator:
    def calculate(
        self,
        contract_type: ContractType,
        gross_monthly: float,
        *,
        business_costs: float = 0.0,
        include_ppk: bool = False,
        include_voluntary_sickness: bool = False,
    ) -> NetSalaryBreakdown:
        if gross_monthly <= 0:
            raise ValueError("gross_monthly must be positive")
        return _STRATEGIES[contract_type].calculate(
            gross_monthly,
            business_costs=business_costs,
            include_ppk=include_ppk,
            include_voluntary_sickness=include_voluntary_sickness,
        )


def net_monthly_take_home(salary: Salary) -> float | None:
    """The salary entry's estimated net monthly PLN take-home, or `None` if it can't
    be calculated (non-PLN currency, an unmapped contract type, or an unnormalizable
    period). Assumes no PPK, no voluntary sickness insurance, and no business costs,
    since those aren't known per offer."""
    if salary.currency != "PLN":
        return None
    contract_type = contract_type_from_label(salary.contract_type)
    if contract_type is None:
        return None
    gross = monthly_gross_amount(salary)
    if gross is None or gross <= 0:
        return None
    return round(SalaryCalculator().calculate(contract_type, gross).take_home, 2)
