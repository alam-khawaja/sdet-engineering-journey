"""Intentionally weak: happy paths and loose assertions, no tier edges, no exact money values."""

import pytest

from demo_sut.tiered_billing import (
    FraudSuspected,
    build_invoice,
    fraud_check,
    subtotal,
    tax,
    tier_discount,
)


def test_bigger_orders_get_bigger_discounts() -> None:
    assert tier_discount(2_000) > tier_discount(700) > tier_discount(200) > tier_discount(10)


def test_subtotal_without_discount() -> None:
    assert subtotal(10, 9.99) == 99.9


def test_subtotal_allows_zero_units() -> None:
    assert subtotal(0, 9.99) == 0


def test_subtotal_rejects_negative_units() -> None:
    with pytest.raises(ValueError):
        subtotal(-1, 9.99)


def test_tax_is_charged() -> None:
    assert tax(100.0, "US-CA") > 0


def test_tax_exempt_customers_pay_nothing() -> None:
    assert tax(100.0, "UK", tax_exempt=True) == 0.0


def test_unknown_region_is_rejected() -> None:
    with pytest.warns(UserWarning), pytest.raises(ValueError):
        tax(100.0, "MARS")


def test_huge_charge_is_blocked() -> None:
    with pytest.raises(FraudSuspected):
        fraud_check(50_000, "US", "US", 0)


def test_country_mismatch_is_blocked() -> None:
    with pytest.raises(FraudSuspected):
        fraud_check(5_000, "US", "NG", 0)


def test_velocity_limit_is_blocked() -> None:
    with pytest.raises(FraudSuspected):
        fraud_check(10, "US", "US", 5)


def test_invoice_total() -> None:
    invoice = build_invoice(150, 10.0, "US-NY")
    assert invoice.total == 1482.0
    assert repr(invoice).startswith("Invoice(")
