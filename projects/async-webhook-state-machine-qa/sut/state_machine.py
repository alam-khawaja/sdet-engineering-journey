"""Order payment state machine and optimistic concurrency (version column) primitives.

Allowed transitions::

    PENDING_PAYMENT --payment.succeeded--> PAID --payment.refunded--> REFUNDED

Every write is a conditional ``UPDATE ... WHERE version = :expected``. If another
writer changed the row first, zero rows match and the caller gets a
``StaleVersionError`` instead of silently overwriting newer state.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from sut.database import Order, OrderStatus, Product, utcnow

ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PendingPayment: frozenset({OrderStatus.Paid}),
    OrderStatus.Paid: frozenset({OrderStatus.Refunded}),
    OrderStatus.Refunded: frozenset(),
}

EVENT_TARGET_STATUS: dict[str, OrderStatus] = {
    "payment.succeeded": OrderStatus.Paid,
    "payment.refunded": OrderStatus.Refunded,
}


class IllegalTransitionError(Exception):
    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Illegal order transition {current.value} -> {target.value}")


class StaleVersionError(Exception):
    def __init__(self, entity: str, entity_id: int, expected_version: int) -> None:
        self.entity = entity
        self.entity_id = entity_id
        self.expected_version = expected_version
        super().__init__(
            f"{entity} {entity_id} was modified concurrently (expected version {expected_version})"
        )


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: OrderStatus, target: OrderStatus) -> None:
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)


def target_status_for_event(event_type: str) -> OrderStatus:
    try:
        return EVENT_TARGET_STATUS[event_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported payment event type: {event_type}") from exc


async def transition_order(session: AsyncSession, order: Order, target: OrderStatus) -> Order:
    """Validate and apply one transition, guarded by the order's current version.

    Must be called inside an open transaction. Returns the refreshed order.
    """
    current = OrderStatus(order.status)
    assert_transition(current, target)

    result = await session.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.version == order.version,
            Order.status == current.value,
        )
        .values(status=target.value, version=Order.version + 1, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise StaleVersionError("Order", order.id, order.version)

    await session.refresh(order)
    return order


async def reserve_stock(
    session: AsyncSession, product_id: int, quantity: int, expected_version: int
) -> bool:
    """Decrement stock only if nobody changed the product since it was read.

    Returns ``False`` on a version conflict or insufficient stock, so the caller
    can re-read and decide between retrying and rejecting.
    """
    result = await session.execute(
        update(Product)
        .where(
            Product.id == product_id,
            Product.version == expected_version,
            Product.stock >= quantity,
        )
        .values(stock=Product.stock - quantity, version=Product.version + 1)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1
