"""FastAPI application: orders, signed payment webhooks, and opt-in test-support endpoints.

Run locally::

    uvicorn sut.app:create_app --factory --port 8000

Environment variables (all optional):

- ``DATABASE_URL``            default ``sqlite+aiosqlite:///./sut.db``
- ``WEBHOOK_SECRET``          default ``whsec_local_dev_only``
- ``WEBHOOK_TOLERANCE_SECONDS`` default ``300``
- ``RUN_WORKER``              default ``1`` (start the job worker in the app lifespan)
- ``ENABLE_TEST_ENDPOINTS``   default ``0`` (expose ``/_test/*`` for black-box suites)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sut.database import (
    Database,
    DeadLetterQueue,
    JobQueue,
    Order,
    OrderStatus,
    PaymentLedger,
    Product,
)
from sut.state_machine import (
    IllegalTransitionError,
    StaleVersionError,
    reserve_stock,
    target_status_for_event,
    transition_order,
)
from sut.worker import FULFILLMENT_PREPARE_JOB, JobWorker

MAX_STOCK_RESERVATION_ATTEMPTS = 50


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite+aiosqlite:///./sut.db"
    webhook_secret: str = "whsec_local_dev_only"
    webhook_tolerance_seconds: int = 300
    run_worker: bool = True
    enable_test_endpoints: bool = False
    worker_poll_interval: float = 0.05
    worker_max_attempts: int = 3
    worker_retry_backoff_seconds: float = 0.05

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", cls.webhook_secret),
            webhook_tolerance_seconds=int(
                os.environ.get("WEBHOOK_TOLERANCE_SECONDS", cls.webhook_tolerance_seconds)
            ),
            run_worker=_env_flag("RUN_WORKER", cls.run_worker),
            enable_test_endpoints=_env_flag("ENABLE_TEST_ENDPOINTS", cls.enable_test_endpoints),
        )


class WebhookAuthError(Exception):
    pass


class _StockVersionConflict(Exception):
    """Another writer changed the product between read and conditional update."""


def compute_webhook_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    """Hex HMAC-SHA256 of ``f"{timestamp}.{raw_body}"``."""
    message = timestamp.encode("utf-8") + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    *,
    secret: str,
    timestamp_header: str | None,
    signature_header: str | None,
    raw_body: bytes,
    tolerance_seconds: int,
    now: float | None = None,
) -> None:
    """Raise ``WebhookAuthError`` unless the request is authentic and fresh.

    The timestamp is part of the signed message, so an attacker cannot refresh an
    old captured request without breaking the signature. Clock skew in either
    direction beyond the tolerance is rejected.
    """
    if not timestamp_header or not signature_header:
        raise WebhookAuthError("Missing X-Timestamp or X-Signature header")

    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise WebhookAuthError("X-Timestamp must be an integer Unix epoch") from exc

    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        raise WebhookAuthError("X-Timestamp is outside the replay window")

    expected = compute_webhook_signature(secret, timestamp_header, raw_body)
    if not hmac.compare_digest(expected, signature_header.strip().lower()):
        raise WebhookAuthError("X-Signature does not match")


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def error_detail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=100)


class OrderResponse(BaseModel):
    order_id: int
    product_id: int
    quantity: int
    amount_cents: int
    status: OrderStatus
    version: int
    fulfillment_status: str
    idempotent_replay: bool = False


class PaymentWebhookEvent(BaseModel):
    event_type: Literal["payment.succeeded", "payment.refunded"]
    order_id: int = Field(gt=0)
    amount_cents: int = Field(ge=0)


class WebhookResponse(BaseModel):
    result: Literal["processed", "duplicate"]
    order_id: int
    order_status: OrderStatus
    version: int


class SeedProductRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=64)
    name: str = Field(default="Test Product", max_length=255)
    price_cents: int = Field(default=1000, ge=0)
    stock: int = Field(ge=0)


class ProductResponse(BaseModel):
    product_id: int
    sku: str
    stock: int
    version: int


class RawJobRequest(BaseModel):
    job_type: str = Field(default=FULFILLMENT_PREPARE_JOB, max_length=64)
    payload: str


class JobResponse(BaseModel):
    job_id: int
    job_type: str
    status: str
    attempts: int
    last_error: str | None


class DeadLetterResponse(BaseModel):
    dlq_id: int
    original_job_id: int
    job_type: str
    payload: str
    attempts: int
    error: str
    traceback: str


class LedgerEntryResponse(BaseModel):
    ledger_id: int
    idempotency_key: str
    event_type: str
    amount_cents: int


def _order_response(order: Order, *, replay: bool = False) -> OrderResponse:
    return OrderResponse(
        order_id=order.id,
        product_id=order.product_id,
        quantity=order.quantity,
        amount_cents=order.amount_cents,
        status=OrderStatus(order.status),
        version=order.version,
        fulfillment_status=order.fulfillment_status,
        idempotent_replay=replay,
    )


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    database: Database = request.app.state.database
    return database.session_factory


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AppSettings = Annotated[Settings, Depends(get_settings)]

api_router = APIRouter()
test_router = APIRouter(prefix="/_test", tags=["test-support"])


@api_router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    worker: JobWorker | None = request.app.state.worker
    return {"status": "ok", "worker_running": bool(worker and worker.is_running)}


async def _find_order_by_key(
    session_factory: async_sessionmaker[AsyncSession], idempotency_key: str
) -> Order | None:
    async with session_factory() as session, session.begin():
        return await session.scalar(select(Order).where(Order.idempotency_key == idempotency_key))


def _replay_or_reject(existing: Order, request_fingerprint: str) -> OrderResponse:
    if existing.request_fingerprint != request_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key was already used with a different request body",
            ),
        )
    return _order_response(existing, replay=True)


@api_router.post("/orders", status_code=status.HTTP_202_ACCEPTED, response_model=OrderResponse)
async def create_order(
    body: CreateOrderRequest,
    session_factory: SessionFactory,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> OrderResponse:
    request_fingerprint = fingerprint(
        json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    )

    existing = await _find_order_by_key(session_factory, idempotency_key)
    if existing is not None:
        return _replay_or_reject(existing, request_fingerprint)

    for _attempt in range(MAX_STOCK_RESERVATION_ATTEMPTS):
        async with session_factory() as session:
            async with session.begin():
                product = await session.get(Product, body.product_id)
                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=error_detail("PRODUCT_NOT_FOUND", "Product does not exist"),
                    )
                if product.stock < body.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=error_detail(
                            "OUT_OF_STOCK",
                            "Not enough stock",
                            available=product.stock,
                            requested=body.quantity,
                        ),
                    )
                observed_version = product.version
                unit_price = product.price_cents

            try:
                async with session.begin():
                    reserved = await reserve_stock(
                        session, body.product_id, body.quantity, observed_version
                    )
                    if not reserved:
                        raise _StockVersionConflict

                    order = Order(
                        idempotency_key=idempotency_key,
                        request_fingerprint=request_fingerprint,
                        product_id=body.product_id,
                        quantity=body.quantity,
                        amount_cents=unit_price * body.quantity,
                        status=OrderStatus.PendingPayment.value,
                        version=1,
                    )
                    session.add(order)
                    await session.flush()
                    session.add(
                        JobQueue(
                            job_type=FULFILLMENT_PREPARE_JOB,
                            payload=json.dumps({"order_id": order.id}),
                        )
                    )
            except _StockVersionConflict:
                continue
            except IntegrityError:
                existing = await _find_order_by_key(session_factory, idempotency_key)
                if existing is None:
                    raise
                return _replay_or_reject(existing, request_fingerprint)

            return _order_response(order)

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=error_detail(
            "CONCURRENT_MODIFICATION",
            "Stock changed too many times concurrently; retry the request",
        ),
    )


@api_router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, session_factory: SessionFactory) -> OrderResponse:
    async with session_factory() as session, session.begin():
        order = await session.get(Order, order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("ORDER_NOT_FOUND", "Order does not exist"),
            )
        return _order_response(order)


@api_router.post("/webhooks/payment", response_model=WebhookResponse)
async def payment_webhook(
    request: Request,
    session_factory: SessionFactory,
    settings: AppSettings,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
    x_timestamp: Annotated[str | None, Header(alias="X-Timestamp")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WebhookResponse:
    raw_body = await request.body()

    try:
        verify_webhook_signature(
            secret=settings.webhook_secret,
            timestamp_header=x_timestamp,
            signature_header=x_signature,
            raw_body=raw_body,
            tolerance_seconds=settings.webhook_tolerance_seconds,
        )
    except WebhookAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("WEBHOOK_UNAUTHORIZED", str(exc)),
        ) from exc

    if not idempotency_key or len(idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required"),
        )

    try:
        event = PaymentWebhookEvent.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_PAYLOAD",
                "Webhook body failed validation",
                errors=json.loads(exc.json(include_url=False)),
            ),
        ) from exc

    payload_fingerprint = fingerprint(raw_body)
    target = target_status_for_event(event.event_type)

    try:
        async with session_factory() as session, session.begin():
            duplicate = await _duplicate_webhook_response(
                session, idempotency_key, payload_fingerprint
            )
            if duplicate is not None:
                return duplicate

            order = await session.get(Order, event.order_id)
            if order is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_detail("ORDER_NOT_FOUND", "Order does not exist"),
                )

            try:
                order = await transition_order(session, order, target)
            except IllegalTransitionError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=error_detail(
                        "ILLEGAL_TRANSITION",
                        str(exc),
                        current_status=exc.current.value,
                        requested_status=exc.target.value,
                    ),
                ) from exc
            except StaleVersionError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=error_detail("CONCURRENT_MODIFICATION", str(exc)),
                ) from exc

            session.add(
                PaymentLedger(
                    idempotency_key=idempotency_key,
                    payload_fingerprint=payload_fingerprint,
                    order_id=order.id,
                    event_type=event.event_type,
                    amount_cents=event.amount_cents,
                )
            )
            response = WebhookResponse(
                result="processed",
                order_id=order.id,
                order_status=OrderStatus(order.status),
                version=order.version,
            )
    except IntegrityError:
        async with session_factory() as session, session.begin():
            duplicate = await _duplicate_webhook_response(
                session, idempotency_key, payload_fingerprint
            )
        if duplicate is None:
            raise
        return duplicate

    return response


async def _duplicate_webhook_response(
    session: AsyncSession, idempotency_key: str, payload_fingerprint: str
) -> WebhookResponse | None:
    entry = await session.scalar(
        select(PaymentLedger).where(PaymentLedger.idempotency_key == idempotency_key)
    )
    if entry is None:
        return None
    if entry.payload_fingerprint != payload_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key was already used with a different webhook body",
            ),
        )
    order = await session.get(Order, entry.order_id)
    assert order is not None
    return WebhookResponse(
        result="duplicate",
        order_id=order.id,
        order_status=OrderStatus(order.status),
        version=order.version,
    )


@test_router.post(
    "/products", status_code=status.HTTP_201_CREATED, response_model=ProductResponse
)
async def seed_product(body: SeedProductRequest, session_factory: SessionFactory) -> ProductResponse:
    async with session_factory() as session, session.begin():
        product = Product(
            sku=body.sku or f"SKU-{time.time_ns()}",
            name=body.name,
            price_cents=body.price_cents,
            stock=body.stock,
            version=1,
        )
        session.add(product)
        await session.flush()
        return ProductResponse(
            product_id=product.id, sku=product.sku, stock=product.stock, version=product.version
        )


@test_router.get("/products/{product_id}", response_model=ProductResponse)
async def read_product(product_id: int, session_factory: SessionFactory) -> ProductResponse:
    async with session_factory() as session, session.begin():
        product = await session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return ProductResponse(
            product_id=product.id, sku=product.sku, stock=product.stock, version=product.version
        )


@test_router.get("/orders/{order_id}/ledger", response_model=list[LedgerEntryResponse])
async def read_ledger(order_id: int, session_factory: SessionFactory) -> list[LedgerEntryResponse]:
    async with session_factory() as session, session.begin():
        entries = await session.scalars(
            select(PaymentLedger).where(PaymentLedger.order_id == order_id).order_by(PaymentLedger.id)
        )
        return [
            LedgerEntryResponse(
                ledger_id=entry.id,
                idempotency_key=entry.idempotency_key,
                event_type=entry.event_type,
                amount_cents=entry.amount_cents,
            )
            for entry in entries
        ]


@test_router.post("/jobs", status_code=status.HTTP_201_CREATED, response_model=JobResponse)
async def enqueue_raw_job(body: RawJobRequest, session_factory: SessionFactory) -> JobResponse:
    """Insert a job exactly as given, with no payload validation (used for poison pills)."""
    async with session_factory() as session, session.begin():
        job = JobQueue(job_type=body.job_type, payload=body.payload)
        session.add(job)
        await session.flush()
        return JobResponse(
            job_id=job.id,
            job_type=job.job_type,
            status=job.status,
            attempts=job.attempts,
            last_error=job.last_error,
        )


@test_router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(session_factory: SessionFactory) -> list[JobResponse]:
    async with session_factory() as session, session.begin():
        jobs = await session.scalars(select(JobQueue).order_by(JobQueue.id))
        return [
            JobResponse(
                job_id=job.id,
                job_type=job.job_type,
                status=job.status,
                attempts=job.attempts,
                last_error=job.last_error,
            )
            for job in jobs
        ]


@test_router.get("/dead-letters", response_model=list[DeadLetterResponse])
async def list_dead_letters(session_factory: SessionFactory) -> list[DeadLetterResponse]:
    async with session_factory() as session, session.begin():
        rows = await session.scalars(select(DeadLetterQueue).order_by(DeadLetterQueue.id))
        return [
            DeadLetterResponse(
                dlq_id=row.id,
                original_job_id=row.original_job_id,
                job_type=row.job_type,
                payload=row.payload,
                attempts=row.attempts,
                error=row.error,
                traceback=row.traceback,
            )
            for row in rows
        ]


@test_router.get("/stats")
async def queue_stats(session_factory: SessionFactory) -> dict[str, Any]:
    async with session_factory() as session, session.begin():
        by_status = dict(
            (await session.execute(select(JobQueue.status, func.count()).group_by(JobQueue.status))).all()
        )
        dead = await session.scalar(select(func.count()).select_from(DeadLetterQueue))
        return {"job_queue": by_status, "dead_letter_queue": dead or 0}


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    """Build the app. Tests inject their own ``Settings`` and per-test ``Database``."""
    resolved_settings = settings or Settings.from_env()
    resolved_database = database or Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await resolved_database.create_all()
        worker: JobWorker | None = None
        if resolved_settings.run_worker:
            worker = JobWorker(
                resolved_database.session_factory,
                poll_interval=resolved_settings.worker_poll_interval,
                max_attempts=resolved_settings.worker_max_attempts,
                retry_backoff_seconds=resolved_settings.worker_retry_backoff_seconds,
            )
            worker.start()
        app.state.worker = worker
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
            await resolved_database.dispose()

    app = FastAPI(
        title="Async Webhook State Machine SUT",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.worker = None
    app.include_router(api_router)
    if resolved_settings.enable_test_endpoints:
        app.include_router(test_router)
    return app
