"""A poison job must be retried, then parked in the DLQ, without starving healthy jobs."""

from __future__ import annotations

import asyncio

import pytest

from sut.worker import JobWorker
from tests.conftest import ApiDriver
from tests.helpers.polling import wait_until

VALID_ORDERS = 5
MAX_ATTEMPTS = 3

POISON_PILLS = [
    pytest.param("fulfillment.prepare", "{this is not json", "PoisonPayloadError", id="malformed-json"),
    pytest.param("fulfillment.prepare", '["order_id", 1]', "PoisonPayloadError", id="json-array"),
    pytest.param("fulfillment.prepare", '{"order_id": "abc"}', "PoisonPayloadError", id="wrong-type"),
    pytest.param("fulfillment.prepare", '{"order_id": 987654321}', "LookupError", id="missing-order"),
    pytest.param("inventory.teleport", '{"order_id": 1}', "PoisonPayloadError", id="unknown-job-type"),
]


@pytest.mark.parametrize(("job_type", "payload", "error_type"), POISON_PILLS)
async def test_poison_job_lands_in_dlq_while_valid_jobs_complete(
    api: ApiDriver,
    worker: JobWorker | None,
    job_type: str,
    payload: str,
    error_type: str,
) -> None:
    product = await api.seed_product(stock=VALID_ORDERS)
    poison_job_id = await api.enqueue_raw_job(payload, job_type=job_type)
    order_responses = await asyncio.gather(
        *(api.create_order(product["product_id"]) for _ in range(VALID_ORDERS))
    )
    assert {r.status_code for r in order_responses} == {202}
    order_ids = [r.json()["order_id"] for r in order_responses]

    async def poison_dead_letter() -> dict | None:
        return next(
            (row for row in await api.dead_letters() if row["original_job_id"] == poison_job_id),
            None,
        )

    dead_letter = await wait_until(
        poison_dead_letter, timeout=10.0, description=f"job {poison_job_id} in dead_letter_queue"
    )

    assert dead_letter["attempts"] == MAX_ATTEMPTS
    assert dead_letter["job_type"] == job_type
    assert dead_letter["payload"] == payload, "DLQ must keep the original payload for replay/forensics"
    assert dead_letter["error"].startswith(error_type)
    assert "Traceback (most recent call last)" in dead_letter["traceback"]
    assert poison_job_id not in {job["job_id"] for job in await api.jobs()}, "poison job must be moved, not copied"

    async def all_orders_prepared() -> list[dict]:
        orders = [await api.get_order(order_id) for order_id in order_ids]
        return orders if all(o["fulfillment_status"] == "PREPARED" for o in orders) else []

    prepared = await wait_until(
        all_orders_prepared, timeout=10.0, description=f"{VALID_ORDERS} orders fulfillment PREPARED"
    )
    assert all(order["status"] == "PENDING_PAYMENT" for order in prepared), "fulfillment must not touch payment state"

    if worker is not None:
        assert worker.is_running, "a poison job must not crash the worker"
        assert worker.stats.dead_lettered == 1
        assert worker.stats.completed == VALID_ORDERS
        assert worker.stats.failed_attempts == MAX_ATTEMPTS


async def test_worker_keeps_processing_new_jobs_after_dead_lettering(
    api: ApiDriver, worker: JobWorker | None
) -> None:
    poison_job_id = await api.enqueue_raw_job("not-json-at-all")
    await wait_until(
        lambda: _contains_dead_letter(api, poison_job_id),
        description=f"job {poison_job_id} in dead_letter_queue",
    )

    order = await api.create_pending_order()

    async def order_prepared() -> bool:
        return (await api.get_order(order["order_id"]))["fulfillment_status"] == "PREPARED"

    await wait_until(order_prepared, description="order created after DLQ event is prepared")


async def test_wait_until_reports_last_observed_state_on_timeout() -> None:
    observations = iter(range(1000))

    with pytest.raises(AssertionError) as excinfo:
        await wait_until(lambda: next(observations) < 0, timeout=0.2, interval=0.02, description="impossible")

    message = str(excinfo.value)
    assert "Timed out" in message
    assert "impossible" in message
    assert "last value: False" in message


async def _contains_dead_letter(api: ApiDriver, job_id: int) -> bool:
    return any(row["original_job_id"] == job_id for row in await api.dead_letters())
