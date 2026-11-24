"""Usage-based SaaS billing: volume discount tiers, regional tax, and fraud guard clauses."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

TAX_RATES: dict[str, float] = {"US-CA": 0.0725, "US-NY": 0.04, "UK": 0.20}
FRAUD_SINGLE_CHARGE_LIMIT = 10_000.0
FRAUD_MISMATCH_LIMIT = 500.0
FRAUD_VELOCITY_LIMIT = 5


class FraudSuspected(Exception):
    """Charge blocked by a fraud guard."""


@dataclass(frozen=True)
class Invoice:
    units: int
    subtotal: float
    tax: float
    total: float

    def __repr__(self) -> str:
        return f"Invoice(units={self.units}, total={self.total:.2f})"


def tier_discount(units: int) -> float:
    if units >= 1000:
        return 0.20
    if units >= 500:
        return 0.10
    if units >= 100:
        return 0.05
    return 0.0


def subtotal(units: int, unit_price: float) -> float:
    if units < 0:
        raise ValueError("units cannot be negative")
    gross = units * unit_price
    return round(gross - gross * tier_discount(units), 2)


def tax(amount: float, region: str, tax_exempt: bool = False) -> float:
    if tax_exempt:
        return 0.0
    rate = TAX_RATES.get(region)
    if rate is None:
        warnings.warn(f"unknown tax region {region}", stacklevel=2)
        raise ValueError(f"unknown tax region {region}")
    return round(amount * rate, 2)


def fraud_check(
    amount: float,
    country: str,
    card_country: str,
    velocity_last_hour: int,
    *,
    block_on_mismatch: bool = True,
) -> None:
    if amount > FRAUD_SINGLE_CHARGE_LIMIT:
        raise FraudSuspected("single charge above limit")
    if block_on_mismatch and country != card_country and amount > FRAUD_MISMATCH_LIMIT:
        raise FraudSuspected("card country does not match billing country")
    if velocity_last_hour >= FRAUD_VELOCITY_LIMIT:
        raise FraudSuspected("too many charges in the last hour")


def build_invoice(
    units: int,
    unit_price: float,
    region: str,
    *,
    tax_exempt: bool = False,
    country: str = "US",
    card_country: str = "US",
    velocity_last_hour: int = 0,
) -> Invoice:
    net = subtotal(units, unit_price)
    tax_due = tax(net, region, tax_exempt)
    total = net + tax_due
    fraud_check(total, country, card_country, velocity_last_hour)
    return Invoice(units=units, subtotal=net, tax=tax_due, total=round(total, 2))
