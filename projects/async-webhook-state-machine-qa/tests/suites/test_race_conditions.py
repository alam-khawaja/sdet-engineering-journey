"""Overselling under concurrency: optimistic locking must let exactly N buyers win N units."""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest
from sqlalchemy import func, select

from sut.database import Database, JobQueue, Order
from tests.conftest import ApiDriver

CONCURRENT_BUYERS = 25


async def _fire_concurrent_orders(api: ApiDriver, product_id: int, buyers: int) -> list:
    return await asyncio.gather(*(api.create_order(product_id) for _ in range(buyers)))


async def test_last_unit_is_sold_exactly_once_under_25_concurrent_orders(api: ApiDriver) -> None:
    product = await api.seed_product(stock=1)

    responses = await _fire_concurrent_orders(api, product["product_id"], CONCURRENT_BUYERS)

    codes = Counter(response.status_code for response in responses)
    assert codes == {202: 1, 409: CONCURRENT_BUYERS - 1}, [r.text for r in responses]

    winner = next(r.json() for r in responses if r.status_code == 202)
    assert winner["status"] == "PENDING_PAYMENT"
    assert winner["version"] == 1

    rejected_codes = {r.json()["detail"]["code"] for r in responses if r.status_code == 409}
    assert rejected_codes == {"OUT_OF_STOCK"}

    final_product = await api.get_product(product["product_id"])
    assert final_product["stock"] == 0
    assert final_product["version"] == 2, "stock must be decremented by exactly one successful write"


@pytest.mark.parametrize("stock", [3, 10])
async def test_concurrent_orders_never_exceed_available_stock(api: ApiDriver, stock: int) -> None:
    product = await api.seed_product(stock=stock)

    responses = await _fire_concurrent_orders(api, product["product_id"], CONCURRENT_BUYERS)

    codes = Counter(response.status_code for response in responses)
    assert codes == {202: stock, 409: CONCURRENT_BUYERS - stock}
    order_ids = {r.json()["order_id"] for r in responses if r.status_code == 202}
    assert len(order_ids) == stock, "each winner must get a distinct order"
    assert (await api.get_product(product["product_id"]))["stock"] == 0


@pytest.mark.local_only
async def test_race_leaves_one_order_row_and_one_fulfillment_job(
    api: ApiDriver, local_database: Database
) -> None:
    product = await api.seed_product(stock=1)

    await _fire_concurrent_orders(api, product["product_id"], CONCURRENT_BUYERS)

    async with local_database.session_factory() as session, session.begin():
        order_rows = await session.scalar(
            select(func.count()).select_from(Order).where(Order.product_id == product["product_id"])
        )
        job_rows = await session.scalar(select(func.count()).select_from(JobQueue))
    assert order_rows == 1, "losers must roll back fully, leaving no orphan orders"
    assert job_rows == 1, "only the winning order may enqueue fulfillment"


async def test_unknown_product_returns_404(api: ApiDriver) -> None:
    response = await api.create_order(product_id=987_654_321)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PRODUCT_NOT_FOUND"


async def test_order_without_idempotency_key_is_rejected(api: ApiDriver) -> None:
    product = await api.seed_product(stock=1)

    response = await api.client.post("/orders", json={"product_id": product["product_id"]})

    assert response.status_code == 422
    assert (await api.get_product(product["product_id"]))["stock"] == 1
