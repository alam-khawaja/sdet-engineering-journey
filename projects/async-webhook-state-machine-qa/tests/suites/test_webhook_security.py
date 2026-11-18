"""Only authentic, fresh webhooks may change state; everything else is a 401 with no side effects."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from tests.conftest import ApiDriver
from tests.helpers.signer import SignedWebhook, WebhookSigner, canonical_event

WebhookFactory = Callable[[WebhookSigner, int], SignedWebhook]


def _tampered_body(signer: WebhookSigner, order_id: int) -> SignedWebhook:
    signed = canonical_event("payment.succeeded", order_id, 1000)
    sent = canonical_event("payment.succeeded", order_id, 1)
    return signer.tampered(signed, sent)


def _invalid_signature(signer: WebhookSigner, order_id: int) -> SignedWebhook:
    return signer.invalid_signature(canonical_event("payment.succeeded", order_id, 1000))


def _expired_timestamp(signer: WebhookSigner, order_id: int) -> SignedWebhook:
    return signer.expired(canonical_event("payment.succeeded", order_id, 1000), age_seconds=301)


def _future_timestamp(signer: WebhookSigner, order_id: int) -> SignedWebhook:
    return signer.valid(
        canonical_event("payment.succeeded", order_id, 1000), timestamp=int(time.time()) + 3600
    )


def _without_header(header: str) -> WebhookFactory:
    def factory(signer: WebhookSigner, order_id: int) -> SignedWebhook:
        signed = signer.event("payment.succeeded", order_id)
        headers = {k: v for k, v in signed.headers.items() if k != header}
        return SignedWebhook(body=signed.body, headers=headers)

    return factory


def _non_numeric_timestamp(signer: WebhookSigner, order_id: int) -> SignedWebhook:
    signed = signer.event("payment.succeeded", order_id)
    return SignedWebhook(body=signed.body, headers={**signed.headers, "X-Timestamp": "yesterday"})


def _replayed_with_fresh_timestamp(signer: WebhookSigner, order_id: int) -> SignedWebhook:
    """Attacker captures an old request and only swaps in a new timestamp."""
    old = signer.expired(canonical_event("payment.succeeded", order_id, 1000), age_seconds=600)
    return SignedWebhook(body=old.body, headers={**old.headers, "X-Timestamp": str(int(time.time()))})


@pytest.mark.parametrize(
    "build_webhook",
    [
        pytest.param(_tampered_body, id="a-tampered-json-body"),
        pytest.param(_invalid_signature, id="b-invalid-hmac-signature"),
        pytest.param(_expired_timestamp, id="c-expired-timestamp-over-5-minutes"),
        pytest.param(_future_timestamp, id="future-timestamp-outside-window"),
        pytest.param(_replayed_with_fresh_timestamp, id="old-signature-fresh-timestamp"),
        pytest.param(_without_header("X-Signature"), id="missing-signature"),
        pytest.param(_without_header("X-Timestamp"), id="missing-timestamp"),
        pytest.param(_non_numeric_timestamp, id="non-numeric-timestamp"),
    ],
)
async def test_untrusted_webhooks_are_rejected_with_401_and_no_side_effects(
    api: ApiDriver, signer: WebhookSigner, build_webhook: WebhookFactory
) -> None:
    order = await api.create_pending_order()

    response = await api.send_webhook(build_webhook(signer, order["order_id"]))

    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "WEBHOOK_UNAUTHORIZED"
    current = await api.get_order(order["order_id"])
    assert (current["status"], current["version"]) == ("PENDING_PAYMENT", 1)
    assert await api.ledger(order["order_id"]) == []


async def test_timestamp_just_inside_replay_window_is_accepted(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()

    response = await api.send_webhook(
        signer.expired(canonical_event("payment.succeeded", order["order_id"], 1000), age_seconds=290)
    )

    assert response.status_code == 200, response.text
    assert (await api.get_order(order["order_id"]))["status"] == "PAID"


async def test_authentic_webhook_without_idempotency_key_returns_400(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()
    signed = signer.event("payment.succeeded", order["order_id"])
    headers = {k: v for k, v in signed.headers.items() if k != "Idempotency-Key"}

    response = await api.send_webhook(SignedWebhook(body=signed.body, headers=headers))

    assert response.status_code == 400
    assert (await api.get_order(order["order_id"]))["status"] == "PENDING_PAYMENT"
