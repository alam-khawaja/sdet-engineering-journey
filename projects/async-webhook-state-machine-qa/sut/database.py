"""Async SQLite (WAL mode) engine, session factory, and ORM models.

SQLite only allows one writer at a time. Every transaction is opened with
``BEGIN IMMEDIATE`` so a transaction that reads and then writes takes the write
lock up front instead of failing with ``SQLITE_BUSY`` when it tries to upgrade.
``busy_timeout`` makes competing writers wait rather than error out.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

BUSY_TIMEOUT_MS = 30_000


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite has no native timezone type)."""
    return datetime.now(UTC).replace(tzinfo=None)


def epoch_now() -> float:
    return time.time()


class OrderStatus(StrEnum):
    PendingPayment = "PENDING_PAYMENT"
    Paid = "PAID"
    Refunded = "REFUNDED"


class FulfillmentStatus(StrEnum):
    NotStarted = "NOT_STARTED"
    Prepared = "PREPARED"


class JobStatus(StrEnum):
    Pending = "PENDING"
    Processing = "PROCESSING"
    Done = "DONE"


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Order(Base):
    """``version`` tracks payment-state transitions only; fulfillment prep does not bump it."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OrderStatus.PendingPayment.value
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fulfillment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FulfillmentStatus.NotStarted.value
    )
    fulfillment_prepared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    product: Mapped[Product] = relationship()
    ledger_entries: Mapped[list[PaymentLedger]] = relationship(back_populates="order")


class PaymentLedger(Base):
    """One row per accepted webhook event; the unique key is the deduplication guarantee."""

    __tablename__ = "payment_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="ledger_entries")


class JobQueue(Base):
    """``payload`` is raw text so a malformed (poison) payload can be stored and must be survived."""

    __tablename__ = "job_queue"
    __table_args__ = (Index("ix_job_queue_claim", "status", "available_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.Pending.value)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[float] = mapped_column(Float, nullable=False, default=epoch_now)
    locked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class DeadLetterQueue(Base):
    __tablename__ = "dead_letter_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[str] = mapped_column(Text, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Database:
    """Owns the async engine and session factory for one SQLite file."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: AsyncEngine = create_async_engine(
            url,
            connect_args={"timeout": BUSY_TIMEOUT_MS / 1000},
            pool_timeout=BUSY_TIMEOUT_MS / 1000,
        )
        self._install_sqlite_hooks(self.engine)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    @staticmethod
    def _install_sqlite_hooks(engine: AsyncEngine) -> None:
        @event.listens_for(engine.sync_engine, "connect")
        def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        @event.listens_for(engine.sync_engine, "begin")
        def _on_begin(connection: Any) -> None:
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    async def create_all(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def journal_mode(self) -> str:
        async with self.engine.connect() as connection:
            result = await connection.exec_driver_sql("PRAGMA journal_mode")
            return str(result.scalar_one())

    async def dispose(self) -> None:
        await self.engine.dispose()
