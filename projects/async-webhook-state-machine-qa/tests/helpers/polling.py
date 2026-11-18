"""Deterministic polling for eventually-consistent assertions.

Tests never sleep for a fixed time and hope the background worker finished.
They poll a predicate until it returns something truthy, or fail with a
message that shows what the system looked like on the last check.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

Predicate = Callable[[], T | Awaitable[T]]


class WaitTimeoutError(AssertionError):
    """Raised when a condition never became true; subclasses AssertionError so pytest reports it as a failure."""


def _describe(value: object, limit: int = 2000) -> str:
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit]}... ({len(text)} chars)"


async def wait_until(
    predicate: Predicate[T],
    timeout: float = 5.0,
    interval: float = 0.05,
    description: str = "condition",
) -> T:
    """Poll ``predicate`` until it returns a truthy value and return that value.

    ``predicate`` may be sync or async. Exceptions raised by the predicate are
    treated as "not yet" and the most recent one is included in the timeout
    diagnostics, so a transient 404 or a missing row does not end the wait early.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if interval <= 0:
        raise ValueError("interval must be positive")

    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + timeout
    attempts = 0
    last_value: object = None
    last_error: BaseException | None = None

    while True:
        attempts += 1
        try:
            result = predicate()
            if inspect.isawaitable(result):
                result = await result
            last_value = result
            last_error = None
            if result:
                return result
        except Exception as exc:
            last_error = exc

        now = loop.time()
        if now >= deadline:
            lines = [
                f"Timed out after {now - started:.2f}s waiting for: {description}",
                f"  attempts:   {attempts} (interval {interval}s, timeout {timeout}s)",
                f"  last value: {_describe(last_value)}",
            ]
            if last_error is not None:
                lines.append(f"  last error: {type(last_error).__name__}: {last_error}")
            raise WaitTimeoutError("\n".join(lines)) from last_error

        await asyncio.sleep(min(interval, deadline - now))
