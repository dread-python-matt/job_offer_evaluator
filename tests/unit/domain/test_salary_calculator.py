import pytest

from app.domain.entities import Salary
from app.domain.salary_calculator import (
    B2B_FULL_ZUS_BASE_2026,
    B2B_RYCZALT_HEALTH_TIER_1_MONTHLY,
    B2B_RYCZALT_HEALTH_TIER_2_MONTHLY,
    B2B_RYCZALT_HEALTH_TIER_3_MONTHLY,
    B2B_RYCZALT_TAX_RATE,
    EMPLOYMENT_KUP_MONTHLY,
    FIRST_BRACKET_RATE,
    HEALTH_INSURANCE_RATE,
    PPK_EMPLOYEE_RATE,
    SECOND_BRACKET_RATE,
    TAX_CREDIT_MONTHLY,
    ContractType,
    SalaryCalculator,
    contract_type_from_label,
    net_monthly_take_home,
)


# These lock in the researched 2026 constants so an accidental edit fails loudly.
def test_2026_constants_match_published_figures():
    assert HEALTH_INSURANCE_RATE == pytest.approx(0.09)
    assert FIRST_BRACKET_RATE == pytest.approx(0.12)
    assert SECOND_BRACKET_RATE == pytest.approx(0.32)
    assert TAX_CREDIT_MONTHLY == pytest.approx(300.0)
    assert EMPLOYMENT_KUP_MONTHLY == pytest.approx(250.0)
    assert PPK_EMPLOYEE_RATE == pytest.approx(0.02)
    assert B2B_RYCZALT_TAX_RATE == pytest.approx(0.12)
    assert B2B_FULL_ZUS_BASE_2026 == pytest.approx(5652.60)
    assert B2B_RYCZALT_HEALTH_TIER_1_MONTHLY == pytest.approx(498.35, abs=0.01)
    assert B2B_RYCZALT_HEALTH_TIER_2_MONTHLY == pytest.approx(830.58, abs=0.01)
    assert B2B_RYCZALT_HEALTH_TIER_3_MONTHLY == pytest.approx(1495.04, abs=0.01)


class TestCalculateRejectsNonPositiveGross:
    @pytest.mark.parametrize(
        "contract_type", [ContractType.B2B, ContractType.EMPLOYMENT, ContractType.CIVIL]
    )
    @pytest.mark.parametrize("gross_monthly", [0.0, -1.0, -1000.0])
    def test_raises_value_error(self, contract_type, gross_monthly):
        with pytest.raises(ValueError, match="gross_monthly must be positive"):
            SalaryCalculator().calculate(contract_type, gross_monthly)


class TestContractTypeFromLabel:
    def test_maps_b2b_label(self):
        assert contract_type_from_label("b2b") is ContractType.B2B

    def test_maps_permanent_label_to_employment(self):
        assert contract_type_from_label("permanent") is ContractType.EMPLOYMENT

    def test_maps_zlecenie_label_to_civil(self):
        assert contract_type_from_label("zlecenie") is ContractType.CIVIL

    def test_is_case_insensitive(self):
        assert contract_type_from_label("B2B") is ContractType.B2B

    def test_returns_none_for_unknown_label(self):
        assert contract_type_from_label("") is None
        assert contract_type_from_label("internship") is None


class TestEmploymentContract:
    def test_take_home_for_a_round_gross_amount(self):
        breakdown = SalaryCalculator().calculate(ContractType.EMPLOYMENT, 10000.0)

        assert breakdown.social_security == pytest.approx(1371.0)
        assert breakdown.health_insurance == pytest.approx(776.61, abs=0.01)
        assert breakdown.income_tax == pytest.approx(705.48, abs=0.01)
        assert breakdown.ppk == 0.0
        assert breakdown.take_home == pytest.approx(7146.91, abs=0.01)

    def test_no_ppk_deducted_by_default(self):
        breakdown = SalaryCalculator().calculate(ContractType.EMPLOYMENT, 10000.0)

        assert breakdown.ppk == 0.0

    def test_deducts_ppk_when_requested(self):
        without_ppk = SalaryCalculator().calculate(ContractType.EMPLOYMENT, 10000.0)
        with_ppk = SalaryCalculator().calculate(ContractType.EMPLOYMENT, 10000.0, include_ppk=True)

        assert with_ppk.ppk == pytest.approx(200.0)
        assert with_ppk.take_home == pytest.approx(without_ppk.take_home - 200.0)

    def test_applies_second_tax_bracket_above_monthly_threshold(self):
        breakdown = SalaryCalculator().calculate(ContractType.EMPLOYMENT, 50000.0)

        assert breakdown.social_security == pytest.approx(6855.0)
        assert breakdown.health_insurance == pytest.approx(3883.05, abs=0.01)
        assert breakdown.income_tax == pytest.approx(11426.4, abs=0.01)
        assert breakdown.take_home == pytest.approx(27835.55, abs=0.01)

    def test_income_tax_never_goes_negative_for_low_gross(self):
        breakdown = SalaryCalculator().calculate(ContractType.EMPLOYMENT, 500.0)

        assert breakdown.income_tax == 0.0
        assert breakdown.take_home > 0.0


class TestCivilContract:
    def test_excludes_voluntary_sickness_by_default(self):
        breakdown = SalaryCalculator().calculate(ContractType.CIVIL, 8000.0)

        assert breakdown.social_security == pytest.approx(900.8, abs=0.01)
        assert breakdown.health_insurance == pytest.approx(638.93, abs=0.01)
        assert breakdown.income_tax == pytest.approx(381.52, abs=0.01)
        assert breakdown.take_home == pytest.approx(6078.75, abs=0.01)

    def test_includes_voluntary_sickness_when_requested(self):
        breakdown = SalaryCalculator().calculate(
            ContractType.CIVIL, 8000.0, include_voluntary_sickness=True
        )

        assert breakdown.social_security == pytest.approx(1096.8, abs=0.01)
        assert breakdown.health_insurance == pytest.approx(621.29, abs=0.01)
        assert breakdown.income_tax == pytest.approx(362.71, abs=0.01)
        assert breakdown.take_home == pytest.approx(5919.2, abs=0.01)

    def test_has_no_ppk_or_business_costs(self):
        breakdown = SalaryCalculator().calculate(ContractType.CIVIL, 8000.0)

        assert breakdown.ppk == 0.0
        assert breakdown.business_costs == 0.0


class TestB2BContract:
    def test_uses_lowest_health_insurance_tier_for_low_annual_revenue(self):
        breakdown = SalaryCalculator().calculate(ContractType.B2B, 4000.0)

        assert breakdown.health_insurance == pytest.approx(B2B_RYCZALT_HEALTH_TIER_1_MONTHLY)

    def test_uses_middle_health_insurance_tier_for_mid_annual_revenue(self):
        breakdown = SalaryCalculator().calculate(ContractType.B2B, 10000.0)

        assert breakdown.health_insurance == pytest.approx(B2B_RYCZALT_HEALTH_TIER_2_MONTHLY)

    def test_uses_highest_health_insurance_tier_for_high_annual_revenue(self):
        breakdown = SalaryCalculator().calculate(ContractType.B2B, 30000.0)

        assert breakdown.health_insurance == pytest.approx(B2B_RYCZALT_HEALTH_TIER_3_MONTHLY)

    def test_social_security_excludes_voluntary_sickness_by_default(self):
        with_sickness = SalaryCalculator().calculate(
            ContractType.B2B, 10000.0, include_voluntary_sickness=True
        )
        without_sickness = SalaryCalculator().calculate(ContractType.B2B, 10000.0)

        assert without_sickness.social_security < with_sickness.social_security
        assert without_sickness.social_security == pytest.approx(1788.48, abs=0.01)

    def test_business_costs_reduce_take_home_but_not_the_tax_base(self):
        without_costs = SalaryCalculator().calculate(ContractType.B2B, 10000.0)
        with_costs = SalaryCalculator().calculate(ContractType.B2B, 10000.0, business_costs=1000.0)

        assert with_costs.income_tax == pytest.approx(without_costs.income_tax)
        assert with_costs.take_home == pytest.approx(without_costs.take_home - 1000.0)

    def test_income_tax_is_ryczalt_rate_on_revenue_minus_ssc_and_half_health(self):
        gross = 10000.0
        breakdown = SalaryCalculator().calculate(ContractType.B2B, gross)

        expected_taxable = gross - breakdown.social_security - breakdown.health_insurance * 0.5
        assert breakdown.income_tax == pytest.approx(expected_taxable * B2B_RYCZALT_TAX_RATE, abs=0.01)


class TestNetMonthlyTakeHome:
    def _salary(self, contract_type="b2b", currency="PLN", period="month", min_amount=10000, max_amount=12000):
        return Salary(
            contract_type=contract_type,
            min_amount=min_amount,
            max_amount=max_amount,
            currency=currency,
            period=period,
        )

    def test_computes_take_home_for_a_normal_pln_b2b_salary(self):
        result = net_monthly_take_home(self._salary())

        assert result is not None
        assert result == pytest.approx(
            SalaryCalculator().calculate(ContractType.B2B, 12000.0).take_home, abs=0.01
        )

    def test_returns_none_for_non_pln_currency(self):
        assert net_monthly_take_home(self._salary(currency="EUR")) is None

    def test_returns_none_for_unmapped_contract_type(self):
        assert net_monthly_take_home(self._salary(contract_type="")) is None

    def test_returns_none_when_period_cannot_be_normalized(self):
        assert net_monthly_take_home(self._salary(period="")) is None

    def test_returns_none_for_zero_gross_instead_of_raising(self):
        assert net_monthly_take_home(self._salary(min_amount=0, max_amount=0)) is None
