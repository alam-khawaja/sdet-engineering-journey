"""Intentionally weak: every line runs, but boundaries and prices are never pinned down.

Coverage reports ~100% here. pymutate shows what that number hides.
"""

import pytest

from demo_sut.credit_underwriting import (
    Applicant,
    Decision,
    debt_to_income,
    price_apr,
    risk_tier,
    underwrite,
)

STRONG = Applicant(annual_income=120_000, monthly_debt=1_500, credit_score=780, employment_months=60)


def test_debt_to_income_is_a_ratio() -> None:
    assert debt_to_income(1_000, 60_000) == pytest.approx(0.2)


def test_debt_to_income_rejects_zero_income() -> None:
    with pytest.raises(ValueError):
        debt_to_income(1_000, 0)


def test_risk_tiers_exist() -> None:
    assert risk_tier(800) == "PRIME"
    assert risk_tier(680) == "NEAR_PRIME"
    assert risk_tier(500) == "SUBPRIME"


def test_price_includes_high_dti_surcharge() -> None:
    assert price_apr("PRIME", 0.10) > 0
    assert price_apr("SUBPRIME", 0.35) == 14.75


def test_rejects_non_positive_loan() -> None:
    with pytest.raises(ValueError):
        underwrite(STRONG, 0)


def test_bankruptcy_is_declined() -> None:
    applicant = Applicant(120_000, 1_500, 780, 60, has_bankruptcy=True)
    assert underwrite(applicant, 10_000, income_verified=True).decision is Decision.DECLINED


def test_unverified_income_is_not_approved() -> None:
    assert underwrite(STRONG, 10_000).decision is not Decision.APPROVED


def test_prime_applicant_is_approved() -> None:
    result = underwrite(STRONG, 50_000, income_verified=True)
    assert result.decision is Decision.APPROVED
    assert result.reasons == ("prime fast-track",)


def test_bad_credit_is_declined() -> None:
    applicant = Applicant(90_000, 4_000, 500, 6)
    result = underwrite(applicant, 900_000, income_verified=True)
    assert result.decision is Decision.DECLINED


def test_thin_employment_history_is_referred() -> None:
    applicant = Applicant(80_000, 1_000, 680, 6)
    result = underwrite(applicant, 20_000, income_verified=True)
    assert result.reasons == ("manual review",)


def test_near_prime_takes_standard_path() -> None:
    applicant = Applicant(80_000, 1_000, 680, 36)
    result = underwrite(applicant, 20_000, income_verified=True)
    assert result.reasons == ("standard approval",)
    assert str(result)
