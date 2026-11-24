"""Consumer loan underwriting: hard declines, debt-to-income limits, risk tiers, and pricing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

MIN_CREDIT_SCORE = 620
PRIME_CREDIT_SCORE = 740
MAX_DTI = 0.43
PRIME_MAX_DTI = 0.36
MAX_LOAN_TO_INCOME = 5
MIN_EMPLOYMENT_MONTHS = 24


class Decision(str, Enum):
    APPROVED = "APPROVED"
    REFERRED = "REFERRED"
    DECLINED = "DECLINED"


@dataclass(frozen=True)
class Applicant:
    annual_income: float
    monthly_debt: float
    credit_score: int
    employment_months: int
    has_bankruptcy: bool = False


@dataclass(frozen=True)
class UnderwritingResult:
    decision: Decision
    rate_apr: float
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.decision.value} at {self.rate_apr:.2f}% APR ({', '.join(self.reasons)})"


def debt_to_income(monthly_debt: float, annual_income: float) -> float:
    """Monthly debt payments divided by gross monthly income."""
    if annual_income <= 0:
        raise ValueError("annual_income must be positive")
    return monthly_debt / (annual_income / 12)


def risk_tier(credit_score: int) -> str:
    if credit_score >= PRIME_CREDIT_SCORE:
        return "PRIME"
    if credit_score >= MIN_CREDIT_SCORE:
        return "NEAR_PRIME"
    return "SUBPRIME"


def price_apr(tier: str, dti: float) -> float:
    rate = {"PRIME": 6.5, "NEAR_PRIME": 9.25, "SUBPRIME": 14.0}[tier]
    if dti > 0.30:
        rate = rate + 0.75
    return round(rate, 2)


def underwrite(
    applicant: Applicant,
    loan_amount: float,
    *,
    require_verification: bool = True,
    income_verified: bool = False,
) -> UnderwritingResult:
    if loan_amount <= 0:
        raise ValueError("loan_amount must be positive")
    if applicant.has_bankruptcy:
        return UnderwritingResult(Decision.DECLINED, 0.0, ("bankruptcy on file",))
    if require_verification and not income_verified:
        return UnderwritingResult(Decision.REFERRED, 0.0, ("income not verified",))

    dti = debt_to_income(applicant.monthly_debt, applicant.annual_income)
    tier = risk_tier(applicant.credit_score)

    reasons: list[str] = []
    if applicant.credit_score < MIN_CREDIT_SCORE:
        reasons.append("credit score below minimum")
    if dti > MAX_DTI:
        reasons.append("debt-to-income above 43%")
    if loan_amount > applicant.annual_income * MAX_LOAN_TO_INCOME:
        reasons.append("loan exceeds 5x annual income")
    if reasons:
        logger.info("declined applicant: %s", reasons)
        return UnderwritingResult(Decision.DECLINED, 0.0, tuple(reasons))

    if tier == "PRIME" and dti <= PRIME_MAX_DTI and applicant.employment_months >= MIN_EMPLOYMENT_MONTHS:
        return UnderwritingResult(Decision.APPROVED, price_apr(tier, dti), ("prime fast-track",))
    if applicant.employment_months < 12 or dti > 0.40:
        return UnderwritingResult(Decision.REFERRED, price_apr(tier, dti), ("manual review",))
    return UnderwritingResult(Decision.APPROVED, price_apr(tier, dti), ("standard approval",))
