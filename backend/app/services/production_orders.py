"""Production orders service (Phase 5.5, #81).

Owns the production-order aggregate plus its membership table. Job-in-an-
active-order is a service-level invariant (not a DB constraint) — adding
a job that's already inside another **active** order raises
:class:`JobAlreadyInActiveOrderError`. Membership inside ``planning`` or
``completed`` / ``archived`` orders does not block adding the same job
elsewhere; that's an explicit operator-affordance for prep + history.

State machine
-------------
``planning`` is the only legal create state. Transitions:

    planning  -> active     (activate)
    active    -> completed  (complete)
    active    -> archived   (archive)
    completed -> archived   (archive)
    planning  -> archived   (archive)

Re-opening is intentionally out of scope. Operators can clone an order
if they need to redo work.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, asc, delete as sa_delete, desc, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import production as production_events
from app.models.job import Job
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderJob,
    ProductionOrderState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reference_number import ReferenceNumberService


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProductionOrdersServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class ProductionOrderNotFoundError(ProductionOrdersServiceError):
    """Mapped to 404."""


class InvalidProductionOrderStateError(ProductionOrdersServiceError):
    """Illegal state transition."""


class JobAlreadyInActiveOrderError(ProductionOrdersServiceError):
    """Service-level guard: a job is already in some *active* order."""


class JobAlreadyInOrderError(ProductionOrdersServiceError):
    """The job is already in *this* order — adding twice is a no-op error."""


class JobNotInOrderError(ProductionOrdersServiceError):
    """remove/reorder targeted a job that isn't in the order."""


class JobNotFoundError(ProductionOrdersServiceError):
    """Mapped to 404."""


class InvalidCursorError(ProductionOrdersServiceError):
    pass


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_TRANSITIONS: dict[ProductionOrderState, frozenset[ProductionOrderState]] = {
    ProductionOrderState.PLANNING: frozenset(
        {ProductionOrderState.ACTIVE, ProductionOrderState.ARCHIVED}
    ),
    ProductionOrderState.ACTIVE: frozenset(
        {ProductionOrderState.COMPLETED, ProductionOrderState.ARCHIVED}
    ),
    ProductionOrderState.COMPLETED: frozenset({ProductionOrderState.ARCHIVED}),
    ProductionOrderState.ARCHIVED: frozenset(),
}


def _ensure_transition(
    current: ProductionOrderState, target: ProductionOrderState
) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidProductionOrderStateError(
            f"cannot transition production order from {current.value} to {target.value}"
        )


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, order_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(order_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Event emission helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=production_events.AGGREGATE_TYPE_PRODUCTION_ORDER,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, order_id: uuid.UUID) -> ProductionOrder:
    stmt = (
        select(ProductionOrder)
        .where(ProductionOrder.id == order_id)
        .options(selectinload(ProductionOrder.jobs))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ProductionOrderNotFoundError(str(order_id))
    # Force a fresh load of the membership collection — the identity map
    # may have cached an earlier version of ``order.jobs`` that doesn't
    # include rows added in this session after the first load.
    await session.refresh(row, ["jobs"])
    return row


async def get(session: AsyncSession, order_id: uuid.UUID) -> ProductionOrder:
    return await _load(session, order_id)


async def create(
    session: AsyncSession,
    *,
    name: str,
    priority: int = 0,
    due_at: datetime | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> ProductionOrder:
    if not name.strip():
        raise ProductionOrdersServiceError("name is required")

    order_number = await ReferenceNumberService.allocate("PO", session=session)

    order = ProductionOrder(
        order_number=order_number,
        name=name.strip(),
        state=ProductionOrderState.PLANNING,
        priority=priority,
        due_at=due_at,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(order)
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_PRODUCTION_ORDER_CREATED,
        aggregate_id=order.id,
        payload={
            "production_order_id": str(order.id),
            "order_number": order.order_number,
            "name": order.name,
            "state": order.state.value,
            "priority": order.priority,
            "due_at": order.due_at.isoformat() if order.due_at else None,
        },
        actor_user_id=actor_user_id,
    )
    return await _load(session, order.id)


_EDITABLE_FIELDS = ("name", "priority", "due_at", "notes")


async def update(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    target = await _load(session, order_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        current = getattr(target, field)
        if isinstance(current, datetime) and isinstance(new_value, datetime):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = current.isoformat() if isinstance(current, datetime) else current
        after[field] = new_value.isoformat() if isinstance(new_value, datetime) else new_value
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_PRODUCTION_ORDER_UPDATED,
        aggregate_id=target.id,
        payload={
            "production_order_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def _transition(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    target: ProductionOrderState,
    event_type: str,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    order = await _load(session, order_id)
    _ensure_transition(order.state, target)
    order.state = target
    await session.flush()
    await _emit(
        session,
        event_type=event_type,
        aggregate_id=order.id,
        payload={"production_order_id": str(order.id)},
        actor_user_id=actor_user_id,
    )
    return order


async def activate(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    return await _transition(
        session,
        order_id=order_id,
        target=ProductionOrderState.ACTIVE,
        event_type=production_events.TYPE_PRODUCTION_ORDER_ACTIVATED,
        actor_user_id=actor_user_id,
    )


async def complete(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    return await _transition(
        session,
        order_id=order_id,
        target=ProductionOrderState.COMPLETED,
        event_type=production_events.TYPE_PRODUCTION_ORDER_COMPLETED,
        actor_user_id=actor_user_id,
    )


async def archive(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    return await _transition(
        session,
        order_id=order_id,
        target=ProductionOrderState.ARCHIVED,
        event_type=production_events.TYPE_PRODUCTION_ORDER_ARCHIVED,
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# Job membership
# ---------------------------------------------------------------------------


async def _job_exists(session: AsyncSession, job_id: uuid.UUID) -> bool:
    return (
        await session.execute(select(exists().where(Job.id == job_id)))
    ).scalar_one()


async def _job_in_active_order(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    exclude_order_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Return the id of an *active* order containing ``job_id`` (else None)."""
    stmt = (
        select(ProductionOrder.id)
        .join(
            ProductionOrderJob,
            ProductionOrderJob.production_order_id == ProductionOrder.id,
        )
        .where(ProductionOrderJob.job_id == job_id)
        .where(ProductionOrder.state == ProductionOrderState.ACTIVE)
    )
    if exclude_order_id is not None:
        stmt = stmt.where(ProductionOrder.id != exclude_order_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _members_ordered(
    session: AsyncSession, order_id: uuid.UUID
) -> list[ProductionOrderJob]:
    stmt = (
        select(ProductionOrderJob)
        .where(ProductionOrderJob.production_order_id == order_id)
        .order_by(asc(ProductionOrderJob.display_order))
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_job(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    job_id: uuid.UUID,
    display_order: int | None = None,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    order = await _load(session, order_id)
    if order.state == ProductionOrderState.ARCHIVED:
        raise InvalidProductionOrderStateError(
            "cannot add a job to an archived production order"
        )

    if not await _job_exists(session, job_id):
        raise JobNotFoundError(str(job_id))

    # Already in this order?
    already = next((m for m in order.jobs if m.job_id == job_id), None)
    if already is not None:
        raise JobAlreadyInOrderError(
            f"job {job_id} is already in production order {order_id}"
        )

    # Service-level guard: at most one active order per job. If this order
    # is the active one, the existing check already excludes it via
    # ``exclude_order_id``; the job being elsewhere-active blocks the add.
    conflict = await _job_in_active_order(
        session, job_id=job_id, exclude_order_id=order_id
    )
    if conflict is not None:
        raise JobAlreadyInActiveOrderError(
            f"job {job_id} is already in active production order {conflict}"
        )

    members = await _members_ordered(session, order_id)
    if display_order is None:
        next_pos = (members[-1].display_order + 1) if members else 0
    else:
        next_pos = max(0, int(display_order))

    membership = ProductionOrderJob(
        production_order_id=order_id,
        job_id=job_id,
        display_order=next_pos,
    )
    session.add(membership)
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_JOB_ADDED_TO_ORDER,
        aggregate_id=order_id,
        payload={
            "production_order_id": str(order_id),
            "job_id": str(job_id),
            "display_order": next_pos,
        },
        actor_user_id=actor_user_id,
    )
    return await _load(session, order_id)


async def remove_job(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    job_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    order = await _load(session, order_id)
    member = next((m for m in order.jobs if m.job_id == job_id), None)
    if member is None:
        raise JobNotInOrderError(f"job {job_id} is not in production order {order_id}")

    await session.execute(
        sa_delete(ProductionOrderJob)
        .where(ProductionOrderJob.production_order_id == order_id)
        .where(ProductionOrderJob.job_id == job_id)
    )
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_JOB_REMOVED_FROM_ORDER,
        aggregate_id=order_id,
        payload={
            "production_order_id": str(order_id),
            "job_id": str(job_id),
        },
        actor_user_id=actor_user_id,
    )
    return await _load(session, order_id)


async def reorder(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    job_id: uuid.UUID,
    new_position: int,
    actor_user_id: uuid.UUID | None,
) -> ProductionOrder:
    if new_position < 0:
        raise ProductionOrdersServiceError("new_position must be >= 0")

    members = await _members_ordered(session, order_id)
    if not members:
        raise ProductionOrderNotFoundError(str(order_id))

    target = next((m for m in members if m.job_id == job_id), None)
    if target is None:
        raise JobNotInOrderError(f"job {job_id} is not in production order {order_id}")

    # Remove the moved item and reinsert at the new index, then renumber.
    remaining = [m for m in members if m.job_id != job_id]
    insert_at = min(new_position, len(remaining))
    new_order = remaining[:insert_at] + [target] + remaining[insert_at:]
    for idx, m in enumerate(new_order):
        if m.display_order != idx:
            m.display_order = idx
    await session.flush()
    return await _load(session, order_id)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@dataclass
class ProductionOrderPage:
    items: list[ProductionOrder]
    next_cursor: str | None


async def list_orders(
    session: AsyncSession,
    *,
    state: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> ProductionOrderPage:
    stmt = select(ProductionOrder).options(selectinload(ProductionOrder.jobs))
    if state is not None:
        try:
            stmt = stmt.where(ProductionOrder.state == ProductionOrderState(state))
        except ValueError as exc:
            raise ProductionOrdersServiceError(f"invalid state filter: {state!r}") from exc
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ProductionOrder.order_number.ilike(like),
                ProductionOrder.name.ilike(like),
            )
        )
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                ProductionOrder.created_at < anchor_ts,
                and_(
                    ProductionOrder.created_at == anchor_ts,
                    ProductionOrder.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(ProductionOrder.created_at), desc(ProductionOrder.id)).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = (
        _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    )
    return ProductionOrderPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidCursorError",
    "InvalidProductionOrderStateError",
    "JobAlreadyInActiveOrderError",
    "JobAlreadyInOrderError",
    "JobNotFoundError",
    "JobNotInOrderError",
    "ProductionOrderNotFoundError",
    "ProductionOrderPage",
    "ProductionOrdersServiceError",
    "activate",
    "add_job",
    "archive",
    "complete",
    "create",
    "get",
    "list_orders",
    "remove_job",
    "reorder",
    "update",
]
