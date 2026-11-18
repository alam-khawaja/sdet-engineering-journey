"""Async background worker over the SQLite ``job_queue`` table.

Lifecycle of one job::

    PENDING --claim--> PROCESSING --handler ok--> DONE
                           |
                           +--handler raises--> attempts += 1
                                 attempts < max  -> PENDING (with backoff)
                                 attempts >= max -> row moved to dead_letter_queue

A handler and the ``DONE`` mark commit in the same transaction, so a crash
mid-handler leaves no half-applied work. A job stuck in ``PROCESSING`` longer
than ``lease_seconds`` (worker died) is claimable again.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sut.database import (
    DeadLetterQueue,
    FulfillmentStatus,
    JobQueue,
    JobStatus,
    Order,
    epoch_now,
    utcnow,
)

logger = logging.getLogger("sut.worker")

FULFILLMENT_PREPARE_JOB = "fulfillment.prepare"

JobHandler = Callable[[AsyncSession, str], Awaitable[None]]


class PoisonPayloadError(ValueError):
    """The payload can never be processed, no matter how many retries."""


async def prepare_fulfillment(session: AsyncSession, payload: str) -> None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PoisonPayloadError(f"Payload is not valid JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise PoisonPayloadError("Payload must be a JSON object")

    order_id = data.get("order_id")
    if not isinstance(order_id, int) or isinstance(order_id, bool):
        raise PoisonPayloadError(f"Payload order_id must be an integer, got {order_id!r}")

    order = await session.get(Order, order_id)
    if order is None:
        raise LookupError(f"Order {order_id} does not exist")

    order.fulfillment_status = FulfillmentStatus.Prepared.value
    order.fulfillment_prepared_at = utcnow()


DEFAULT_HANDLERS: dict[str, JobHandler] = {
    FULFILLMENT_PREPARE_JOB: prepare_fulfillment,
}


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    job_type: str
    payload: str
    attempts: int


@dataclass
class WorkerStats:
    completed: int = 0
    failed_attempts: int = 0
    dead_lettered: int = 0
    loop_errors: int = 0


@dataclass
class JobWorker:
    session_factory: async_sessionmaker[AsyncSession]
    poll_interval: float = 0.05
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.05
    lease_seconds: float = 30.0
    handlers: dict[str, JobHandler] = field(default_factory=lambda: dict(DEFAULT_HANDLERS))
    stats: WorkerStats = field(default_factory=WorkerStats)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> asyncio.Task[None]:
        if self.is_running:
            raise RuntimeError("Worker is already running")
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self.run_forever(), name="job-queue-worker")
        return self._task

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def run_forever(self) -> None:
        logger.info("Worker started (max_attempts=%s)", self.max_attempts)
        while not self._stop_event.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                self.stats.loop_errors += 1
                logger.exception("Worker loop error; continuing")
                processed = False

            if not processed:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass
        logger.info("Worker stopped: %s", self.stats)

    async def run_once(self) -> bool:
        """Claim and process at most one job. Returns ``True`` if a job was claimed."""
        job = await self._claim_next_job()
        if job is None:
            return False

        handler = self.handlers.get(job.job_type)
        try:
            if handler is None:
                raise PoisonPayloadError(f"No handler registered for job type {job.job_type!r}")
            async with self.session_factory() as session, session.begin():
                await handler(session, job.payload)
                stored = await session.get(JobQueue, job.id)
                if stored is not None:
                    stored.status = JobStatus.Done.value
                    stored.locked_at = None
                    stored.completed_at = utcnow()
            self.stats.completed += 1
        except Exception as exc:
            await self._record_failure(job, exc, traceback.format_exc())
        return True

    async def _claim_next_job(self) -> ClaimedJob | None:
        async with self.session_factory() as session, session.begin():
            now = epoch_now()
            job = await session.scalar(
                select(JobQueue)
                .where(
                    or_(
                        and_(
                            JobQueue.status == JobStatus.Pending.value,
                            JobQueue.available_at <= now,
                        ),
                        and_(
                            JobQueue.status == JobStatus.Processing.value,
                            JobQueue.locked_at < now - self.lease_seconds,
                        ),
                    )
                )
                .order_by(JobQueue.available_at, JobQueue.id)
                .limit(1)
            )
            if job is None:
                return None

            job.status = JobStatus.Processing.value
            job.locked_at = now
            return ClaimedJob(
                id=job.id, job_type=job.job_type, payload=job.payload, attempts=job.attempts
            )

    async def _record_failure(self, job: ClaimedJob, exc: Exception, tb: str) -> None:
        error = f"{type(exc).__name__}: {exc}"
        try:
            async with self.session_factory() as session, session.begin():
                stored = await session.get(JobQueue, job.id)
                if stored is None:
                    return

                stored.attempts += 1
                stored.last_error = error

                if stored.attempts >= self.max_attempts:
                    session.add(
                        DeadLetterQueue(
                            original_job_id=stored.id,
                            job_type=stored.job_type,
                            payload=stored.payload,
                            attempts=stored.attempts,
                            error=error,
                            traceback=tb,
                        )
                    )
                    await session.delete(stored)
                    self.stats.dead_lettered += 1
                    logger.warning(
                        "Job %s moved to dead_letter_queue after %s attempts: %s",
                        job.id,
                        stored.attempts,
                        error,
                    )
                else:
                    stored.status = JobStatus.Pending.value
                    stored.locked_at = None
                    stored.available_at = epoch_now() + self.retry_backoff_seconds * (
                        2 ** (stored.attempts - 1)
                    )
                    logger.info(
                        "Job %s failed attempt %s/%s: %s",
                        job.id,
                        stored.attempts,
                        self.max_attempts,
                        error,
                    )
            self.stats.failed_attempts += 1
        except Exception:
            self.stats.loop_errors += 1
            logger.exception("Could not record failure for job %s; lease expiry will retry it", job.id)
