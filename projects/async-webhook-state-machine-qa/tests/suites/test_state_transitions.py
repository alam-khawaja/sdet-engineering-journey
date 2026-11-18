"""Out-of-order and illegal events must never move an order into an invalid state."""

from __future__ import annotations

import pytest

from tests.conftest import ApiDriver
from tests.helpers.signer import WebhookSigner


async def test_refund_before_payment_is_rejected_then_payment_succeeds(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()

    early_refund = await api.send_webhook(signer.event("payment.refunded", order["order_id"]))

    assert early_refund.status_code == 422
    detail = early_refund.json()["detail"]
    assert detail["code"] == "ILLEGAL_TRANSITION"
    assert detail["current_status"] == "PENDING_PAYMENT"
    assert detail["requested_status"] == "REFUNDED"
    unchanged = await api.get_order(order["order_id"])
    assert unchanged["status"] == "PENDING_PAYMENT"
    assert unchanged["version"] == 1
    assert await api.ledger(order["order_id"]) == [], "rejected events must not be recorded"

    payment = await api.send_webhook(signer.event("payment.succeeded", order["order_id"]))

    assert payment.status_code == 200
    assert payment.json()["order_status"] == "PAID"
    paid = await api.get_order(order["order_id"])
    assert paid["status"] == "PAID"
    assert paid["version"] == 2


async def test_full_lifecycle_pending_paid_refunded_bumps_version_each_step(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()

    for event_type, expected_status, expected_version in [
        ("payment.succeeded", "PAID", 2),
        ("payment.refunded", "REFUNDED", 3),
    ]:
        response = await api.send_webhook(signer.event(event_type, order["order_id"]))
        assert response.status_code == 200, response.text
        current = await api.get_order(order["order_id"])
        assert (current["status"], current["version"]) == (expected_status, expected_version)

    assert [entry["event_type"] for entry in await api.ledger(order["order_id"])] == [
        "payment.succeeded",
        "payment.refunded",
    ]


@pytest.mark.parametrize(
    ("setup_events", "illegal_event", "stuck_status"),
    [
        pytest.param(["payment.succeeded"], "payment.succeeded", "PAID", id="paid-to-paid"),
        pytest.param(
            ["payment.succeeded", "payment.refunded"], "payment.succeeded", "REFUNDED", id="refunded-to-paid"
        ),
        pytest.param(
            ["payment.succeeded", "payment.refunded"], "payment.refunded", "REFUNDED", id="refunded-to-refunded"
        ),
    ],
)
async def test_illegal_transitions_are_rejected_with_422(
    api: ApiDriver,
    signer: WebhookSigner,
    setup_events: list[str],
    illegal_event: str,
    stuck_status: str,
) -> None:
    order = await api.create_pending_order()
    for event_type in setup_events:
        assert (await api.send_webhook(signer.event(event_type, order["order_id"]))).status_code == 200
    before = await api.get_order(order["order_id"])

    response = await api.send_webhook(signer.event(illegal_event, order["order_id"]))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ILLEGAL_TRANSITION"
    after = await api.get_order(order["order_id"])
    assert after["status"] == stuck_status
    assert after["version"] == before["version"]
    assert len(await api.ledger(order["order_id"])) == len(setup_events)


async def test_event_for_unknown_order_returns_404(api: ApiDriver, signer: WebhookSigner) -> None:
    response = await api.send_webhook(signer.event("payment.succeeded", 987_654_321))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ORDER_NOT_FOUND"


async def test_signed_but_malformed_event_returns_422(api: ApiDriver, signer: WebhookSigner) -> None:
    response = await api.send_webhook(signer.valid(b'{"event_type": "payment.teleported", "order_id": 1}'))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PAYLOAD"
