"""At-least-once delivery: replays of the same event must have exactly one effect."""

from __future__ import annotations

import asyncio
from collections import Counter

from tests.conftest import ApiDriver, new_key
from tests.helpers.signer import WebhookSigner, canonical_event

REPLAYS = 15


async def test_payment_webhook_replayed_15x_concurrently_is_applied_once(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()
    webhook = signer.event("payment.succeeded", order["order_id"], order["amount_cents"])

    responses = await asyncio.gather(*(api.send_webhook(webhook) for _ in range(REPLAYS)))

    assert {r.status_code for r in responses} == {200}, [r.text for r in responses]
    results = Counter(r.json()["result"] for r in responses)
    assert results == {"processed": 1, "duplicate": REPLAYS - 1}

    ledger = await api.ledger(order["order_id"])
    assert len(ledger) == 1, f"expected a single charge, ledger={ledger}"
    assert ledger[0]["idempotency_key"] == webhook.headers["Idempotency-Key"]

    current = await api.get_order(order["order_id"])
    assert current["status"] == "PAID"
    assert current["version"] == order["version"] + 1, "state must transition exactly once"


async def test_late_replay_after_processing_returns_200_without_side_effects(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()
    webhook = signer.event("payment.succeeded", order["order_id"], order["amount_cents"])
    first = await api.send_webhook(webhook)
    assert first.status_code == 200
    assert first.json()["result"] == "processed"

    replay = await api.send_webhook(webhook)

    assert replay.status_code == 200
    assert replay.json()["result"] == "duplicate"
    assert len(await api.ledger(order["order_id"])) == 1
    assert (await api.get_order(order["order_id"]))["version"] == 2


async def test_webhook_key_reused_with_different_body_is_rejected(
    api: ApiDriver, signer: WebhookSigner
) -> None:
    order = await api.create_pending_order()
    key = new_key("evt")
    assert (
        await api.send_webhook(signer.event("payment.succeeded", order["order_id"], idempotency_key=key))
    ).status_code == 200

    conflicting = signer.valid(
        canonical_event("payment.refunded", order["order_id"], 1000), idempotency_key=key
    )
    response = await api.send_webhook(conflicting)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (await api.get_order(order["order_id"]))["status"] == "PAID"


async def test_order_creation_replayed_concurrently_reserves_stock_once(api: ApiDriver) -> None:
    product = await api.seed_product(stock=5)
    key = new_key("order")

    responses = await asyncio.gather(
        *(api.create_order(product["product_id"], idempotency_key=key) for _ in range(10))
    )

    assert {r.status_code for r in responses} == {202}, [r.text for r in responses]
    assert len({r.json()["order_id"] for r in responses}) == 1
    assert sum(not r.json()["idempotent_replay"] for r in responses) == 1
    assert (await api.get_product(product["product_id"]))["stock"] == 4


async def test_order_key_reused_with_different_body_is_rejected(api: ApiDriver) -> None:
    product = await api.seed_product(stock=5)
    key = new_key("order")
    assert (await api.create_order(product["product_id"], idempotency_key=key)).status_code == 202

    response = await api.create_order(product["product_id"], idempotency_key=key, quantity=2)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (await api.get_product(product["product_id"]))["stock"] == 4
