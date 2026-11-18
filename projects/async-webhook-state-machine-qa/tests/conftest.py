"""Shared fixtures.

Two execution modes, chosen by the ``BASE_URL`` environment variable:

- **Local (default):** each test gets its own SQLite file under ``tmp_path``, an
  in-process app driven through ``httpx.ASGITransport``, and (on request) its own
  background worker. Nothing is shared between tests.
- **Remote (``BASE_URL=http://host:port``):** the same suites run black-box over
  HTTP against a deployed SUT started with ``ENABLE_TEST_ENDPOINTS=1`` and the same
  ``WEBHOOK_SECRET``. Tests marked ``local_only`` are skipped.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from sut.app import Settings, create_app
from sut.database import Database
from sut.worker import JobWorker
from tests.helpers.signer import SignedWebhook, WebhookSigner

BASE_URL = os.environ.get("BASE_URL", "").strip() or None
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "whsec_test_suite_secret")
IS_REMOTE = BASE_URL is not None


def pytest_report_header(config: pytest.Config) -> str:
    target = BASE_URL if IS_REMOTE else "in-process ASGI app, isolated SQLite per test"
    return f"SUT target: {target}"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not IS_REMOTE:
        return
    skip_remote = pytest.mark.skip(reason="needs direct DB access; BASE_URL is set")
    for item in items:
        if "local_only" in item.keywords:
            item.add_marker(skip_remote)


def new_key(prefix: str = "key") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ApiDriver:
    """Thin, intention-revealing wrapper over the SUT's HTTP surface."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def seed_product(self, stock: int, price_cents: int = 1000) -> dict[str, Any]:
        response = await self.client.post(
            "/_test/products", json={"stock": stock, "price_cents": price_cents}
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def get_product(self, product_id: int) -> dict[str, Any]:
        response = await self.client.get(f"/_test/products/{product_id}")
        assert response.status_code == 200, response.text
        return response.json()

    async def create_order(
        self, product_id: int, *, idempotency_key: str | None = None, quantity: int = 1
    ) -> httpx.Response:
        return await self.client.post(
            "/orders",
            json={"product_id": product_id, "quantity": quantity},
            headers={"Idempotency-Key": idempotency_key or new_key("order")},
        )

    async def create_pending_order(self, stock: int = 10, price_cents: int = 1000) -> dict[str, Any]:
        product = await self.seed_product(stock=stock, price_cents=price_cents)
        response = await self.create_order(product["product_id"])
        assert response.status_code == 202, response.text
        order = response.json()
        assert order["status"] == "PENDING_PAYMENT"
        return order

    async def get_order(self, order_id: int) -> dict[str, Any]:
        response = await self.client.get(f"/orders/{order_id}")
        assert response.status_code == 200, response.text
        return response.json()

    async def ledger(self, order_id: int) -> list[dict[str, Any]]:
        response = await self.client.get(f"/_test/orders/{order_id}/ledger")
        assert response.status_code == 200, response.text
        return response.json()

    async def send_webhook(self, webhook: SignedWebhook) -> httpx.Response:
        return await self.client.post("/webhooks/payment", **webhook.as_request_kwargs())

    async def enqueue_raw_job(self, payload: str, job_type: str = "fulfillment.prepare") -> int:
        response = await self.client.post(
            "/_test/jobs", json={"job_type": job_type, "payload": payload}
        )
        assert response.status_code == 201, response.text
        return response.json()["job_id"]

    async def jobs(self) -> list[dict[str, Any]]:
        response = await self.client.get("/_test/jobs")
        assert response.status_code == 200, response.text
        return response.json()

    async def dead_letters(self) -> list[dict[str, Any]]:
        response = await self.client.get("/_test/dead-letters")
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def webhook_secret() -> str:
    return WEBHOOK_SECRET


@pytest.fixture
def signer(webhook_secret: str) -> WebhookSigner:
    return WebhookSigner(secret=webhook_secret)


@pytest.fixture
async def database(tmp_path: Any) -> AsyncIterator[Database | None]:
    if IS_REMOTE:
        yield None
        return
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'sut.db'}")
    await db.create_all()
    try:
        yield db
    finally:
        await db.dispose()


@pytest.fixture
def local_database(database: Database | None) -> Database:
    """For ``local_only`` tests that assert directly against tables."""
    if database is None:
        pytest.skip("direct DB access is unavailable when BASE_URL is set")
    return database


@pytest.fixture
def app(database: Database | None, webhook_secret: str) -> FastAPI | None:
    if database is None:
        return None
    settings = Settings(
        database_url=database.url,
        webhook_secret=webhook_secret,
        run_worker=False,
        enable_test_endpoints=True,
    )
    return create_app(settings=settings, database=database)


@pytest.fixture
async def worker(database: Database | None) -> AsyncIterator[JobWorker | None]:
    """Starts a real background worker for this test's DB. Remote: the server runs its own."""
    if database is None:
        yield None
        return
    job_worker = JobWorker(
        database.session_factory,
        poll_interval=0.02,
        max_attempts=3,
        retry_backoff_seconds=0.02,
    )
    job_worker.start()
    try:
        yield job_worker
    finally:
        await job_worker.stop()


@pytest.fixture
async def client(app: FastAPI | None) -> AsyncIterator[httpx.AsyncClient]:
    if IS_REMOTE:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as remote_client:
            yield remote_client
        return
    assert app is not None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://sut.local", timeout=30.0) as local_client:
        yield local_client


@pytest.fixture
def api(client: httpx.AsyncClient) -> ApiDriver:
    return ApiDriver(client)
