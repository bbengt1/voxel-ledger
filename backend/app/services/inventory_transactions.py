"""Inventory-transactions service (Phase 3.2, #51).

Every physical stock movement — production output, sale, adjustment,
return, waste, receipt, transfer — appends one (or, for transfers, two)
``inventory_transaction`` rows and emits a matching
``inventory.TransactionRecorded`` event in the same transaction. The
table is **append-only**: Postgres rejects UPDATE/DELETE via a trigger
(see migration 0015).

Sign convention
---------------
Callers pass the **positive magnitude** of every kind except
``adjustment``. The service then applies the sign from
:data:`app.models.inventory_transaction.POSITIVE_KINDS` /
:data:`NEGATIVE_KINDS`. For ``adjustment`` the caller's quantity is
treated as a signed delta (positive bumps stock up, negative subtracts).
Passing a non-positive value to any non-adjustment kind raises
``InventoryQuantityError`` mapped to HTTP 400 by the router. This keeps
the API honest: the kind determines direction, not the sign of the
number you happened to pass.

Polymorphic entities
--------------------
``entity_kind`` is one of ``material``, ``supply``, ``product``;
``entity_id`` points into the matching table. There is no FK because
the target varies; the service hand-checks existence + archive status
before inserting. This mirrors the BOM service from #40.

Transfer pairs
--------------
A transfer is one ``transfer_out`` at the source plus one
``transfer_in`` at the destination, sharing a freshly generated
``transfer_pair_id``. Both inserts and both events live in the caller's
transaction; if either fails, the whole thing rolls back atomically.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import inventory as inventory_events
from app.models.inventory_location import InventoryLocation
from app.models.inventory_transaction import (
    ENTITY_KIND_MATERIAL,
    ENTITY_KIND_PRODUCT,
    ENTITY_KIND_SUPPLY,
    INVENTORY_ENTITY_KIND_VALUES,
    INVENTORY_TRANSACTION_KIND_VALUES,
    KIND_ADJUSTMENT,
    NEGATIVE_KINDS,
    POSITIVE_KINDS,
    InventoryTransaction,
)
from app.models.material import Material
from app.models.product import Product
from app.models.supply import Supply
from app.schemas.events import EventCreate
from app.services import event_store


class InventoryTransactionsServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted otherwise."""


class InvalidKindError(InventoryTransactionsServiceError):
    pass


class InvalidEntityKindError(InventoryTransactionsServiceError):
    pass


class InventoryQuantityError(InventoryTransactionsServiceError):
    """Caller-supplied magnitude was non-positive (or zero for
    non-adjustment kinds). Mapped to 400."""


class EntityNotFoundError(InventoryTransactionsServiceError):
    """The polymorphic ``(entity_kind, entity_id)`` did not resolve.
    Mapped to 404."""


class EntityArchivedError(InventoryTransactionsServiceError):
    """Target entity is archived; the ledger refuses to move ghost
    stock. Mapped to 400."""


class LocationNotFoundError(InventoryTransactionsServiceError):
    """Mapped to 404."""


class LocationArchivedError(InventoryTransactionsServiceError):
    """Mapped to 400."""


class TransferLocationsError(InventoryTransactionsServiceError):
    """Source and destination must differ. Mapped to 400."""


class InvalidCursorError(InventoryTransactionsServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_kind(kind: str) -> str:
    if kind not in INVENTORY_TRANSACTION_KIND_VALUES:
        raise InvalidKindError(f"invalid kind: {kind!r}")
    return kind


def _coerce_entity_kind(entity_kind: str) -> str:
    if entity_kind not in INVENTORY_ENTITY_KIND_VALUES:
        raise InvalidEntityKindError(f"invalid entity_kind: {entity_kind!r}")
    return entity_kind


def _apply_sign(kind: str, quantity: Decimal) -> Decimal:
    """Return the signed quantity to persist for ``kind``.

    Rules:
        * ``adjustment`` — caller-supplied sign is preserved; zero
          rejected to avoid no-op rows.
        * positive kinds — magnitude must be > 0; persisted as-is.
        * negative kinds — magnitude must be > 0; sign flipped to
          negative.

    Raises ``InventoryQuantityError`` on any rule violation. The 400
    message reminds the caller that kind drives sign, not the input.
    """
    if quantity == 0:
        raise InventoryQuantityError("quantity must be non-zero")
    if kind == KIND_ADJUSTMENT:
        return quantity
    if quantity < 0:
        raise InventoryQuantityError(
            "magnitude must be positive; the transaction kind determines sign"
        )
    if kind in POSITIVE_KINDS:
        return quantity
    if kind in NEGATIVE_KINDS:
        return -quantity
    # Defensive — _coerce_kind already validated the value.
    raise InvalidKindError(f"unhandled kind: {kind!r}")


_ENTITY_MODELS: dict[str, type] = {
    ENTITY_KIND_MATERIAL: Material,
    ENTITY_KIND_SUPPLY: Supply,
    ENTITY_KIND_PRODUCT: Product,
}


async def _check_entity(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
) -> None:
    """Confirm the polymorphic ref exists and isn't archived."""
    model = _ENTITY_MODELS[entity_kind]
    stmt = select(model.id, model.is_archived).where(model.id == entity_id)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise EntityNotFoundError(f"no {entity_kind} found with id {entity_id}")
    if row[1]:
        raise EntityArchivedError(
            f"{entity_kind} {entity_id} is archived; cannot transact on archived entities"
        )


async def _check_location(
    session: AsyncSession,
    *,
    location_id: uuid.UUID,
) -> InventoryLocation:
    stmt = select(InventoryLocation).where(InventoryLocation.id == location_id)
    loc = (await session.execute(stmt)).scalar_one_or_none()
    if loc is None:
        raise LocationNotFoundError(f"no inventory location with id {location_id}")
    if loc.is_archived:
        raise LocationArchivedError(f"inventory location {location_id} is archived")
    return loc


def _encode_cursor(occurred_at: datetime, tx_id: uuid.UUID) -> str:
    raw = json.dumps({"o": occurred_at.isoformat(), "i": str(tx_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["o"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _emit_recorded(
    session: AsyncSession,
    *,
    tx: InventoryTransaction,
    actor_user_id: uuid.UUID | None,
) -> None:
    payload: dict[str, Any] = {
        "transaction_id": str(tx.id),
        "kind": tx.kind,
        "entity_kind": tx.entity_kind,
        "entity_id": str(tx.entity_id),
        "location_id": str(tx.location_id),
        "signed_quantity": str(tx.quantity),
        "unit_cost": (
            str(tx.unit_cost_at_transaction) if tx.unit_cost_at_transaction is not None else None
        ),
        "total_cost": (
            str(tx.total_cost_at_transaction) if tx.total_cost_at_transaction is not None else None
        ),
        "transfer_pair_id": (str(tx.transfer_pair_id) if tx.transfer_pair_id is not None else None),
        "linked_job_id": (str(tx.linked_job_id) if tx.linked_job_id is not None else None),
        "linked_sale_id": (str(tx.linked_sale_id) if tx.linked_sale_id is not None else None),
        "reason": tx.reason,
    }
    await event_store.append(
        EventCreate(
            type=inventory_events.TYPE_TRANSACTION_RECORDED,
            aggregate_type=inventory_events.AGGREGATE_TYPE_INVENTORY_TRANSACTION,
            aggregate_id=tx.id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def record(
    session: AsyncSession,
    *,
    kind: str,
    entity_kind: str,
    entity_id: uuid.UUID,
    location_id: uuid.UUID,
    quantity: Decimal,
    actor_user_id: uuid.UUID | None,
    occurred_at: datetime | None = None,
    reason: str | None = None,
    unit_cost: Decimal | None = None,
    linked_job_id: uuid.UUID | None = None,
    linked_sale_id: uuid.UUID | None = None,
    transfer_pair_id: uuid.UUID | None = None,
) -> InventoryTransaction:
    """Insert one transaction row and emit ``TransactionRecorded``.

    Does NOT commit; the caller owns the transaction so an outer
    rollback discards both row and event atomically.
    """
    kind = _coerce_kind(kind)
    entity_kind = _coerce_entity_kind(entity_kind)
    if not isinstance(quantity, Decimal):
        quantity = Decimal(str(quantity))
    if unit_cost is not None and not isinstance(unit_cost, Decimal):
        unit_cost = Decimal(str(unit_cost))

    signed = _apply_sign(kind, quantity)
    # Validate refs after sign check so 400s land in a consistent order.
    await _check_entity(session, entity_kind=entity_kind, entity_id=entity_id)
    await _check_location(session, location_id=location_id)

    # total = abs(signed) * unit_cost so cost stays positive even on
    # outbound movements. Downstream consumers treat total_cost as
    # "value of the move" — sign lives on quantity.
    total_cost: Decimal | None = None
    if unit_cost is not None:
        total_cost = abs(signed) * unit_cost

    tx = InventoryTransaction(
        kind=kind,
        entity_kind=entity_kind,
        entity_id=entity_id,
        location_id=location_id,
        quantity=signed,
        unit_cost_at_transaction=unit_cost,
        total_cost_at_transaction=total_cost,
        transfer_pair_id=transfer_pair_id,
        linked_job_id=linked_job_id,
        linked_sale_id=linked_sale_id,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    if occurred_at is not None:
        tx.occurred_at = occurred_at
    session.add(tx)
    await session.flush()

    await _emit_recorded(session, tx=tx, actor_user_id=actor_user_id)
    return tx


async def record_transfer(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    from_location_id: uuid.UUID,
    to_location_id: uuid.UUID,
    quantity: Decimal,
    actor_user_id: uuid.UUID | None,
    occurred_at: datetime | None = None,
    reason: str | None = None,
) -> tuple[InventoryTransaction, InventoryTransaction]:
    """Record two paired rows (``transfer_out``/``transfer_in``).

    Both rows share a fresh ``transfer_pair_id`` so the two halves can
    be reassembled by index lookup. ``quantity`` is the positive
    magnitude; sign is applied per side.
    """
    if from_location_id == to_location_id:
        raise TransferLocationsError("transfer source and destination must differ")
    pair_id = uuid.uuid4()
    out_tx = await record(
        session,
        kind="transfer_out",
        entity_kind=entity_kind,
        entity_id=entity_id,
        location_id=from_location_id,
        quantity=quantity,
        actor_user_id=actor_user_id,
        occurred_at=occurred_at,
        reason=reason,
        transfer_pair_id=pair_id,
    )
    in_tx = await record(
        session,
        kind="transfer_in",
        entity_kind=entity_kind,
        entity_id=entity_id,
        location_id=to_location_id,
        quantity=quantity,
        actor_user_id=actor_user_id,
        occurred_at=occurred_at,
        reason=reason,
        transfer_pair_id=pair_id,
    )
    return out_tx, in_tx


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class InventoryTransactionPage:
    items: list[InventoryTransaction]
    next_cursor: str | None


async def list_transactions(
    session: AsyncSession,
    *,
    entity_kind: str | None = None,
    entity_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    kind: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> InventoryTransactionPage:
    stmt = select(InventoryTransaction)
    if entity_kind is not None:
        stmt = stmt.where(InventoryTransaction.entity_kind == _coerce_entity_kind(entity_kind))
    if entity_id is not None:
        stmt = stmt.where(InventoryTransaction.entity_id == entity_id)
    if location_id is not None:
        stmt = stmt.where(InventoryTransaction.location_id == location_id)
    if kind is not None:
        stmt = stmt.where(InventoryTransaction.kind == _coerce_kind(kind))
    if from_at is not None:
        stmt = stmt.where(InventoryTransaction.occurred_at >= from_at)
    if to_at is not None:
        stmt = stmt.where(InventoryTransaction.occurred_at <= to_at)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                InventoryTransaction.occurred_at < anchor_ts,
                and_(
                    InventoryTransaction.occurred_at == anchor_ts,
                    InventoryTransaction.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(
        desc(InventoryTransaction.occurred_at), desc(InventoryTransaction.id)
    ).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].occurred_at, rows[-1].id) if (rows and has_more) else None
    return InventoryTransactionPage(items=rows, next_cursor=next_cursor)


async def get(session: AsyncSession, transaction_id: uuid.UUID) -> InventoryTransaction:
    stmt = select(InventoryTransaction).where(InventoryTransaction.id == transaction_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise EntityNotFoundError(f"no inventory_transaction with id {transaction_id}")
    return row


__all__ = [
    "EntityArchivedError",
    "EntityNotFoundError",
    "InvalidCursorError",
    "InvalidEntityKindError",
    "InvalidKindError",
    "InventoryQuantityError",
    "InventoryTransactionPage",
    "InventoryTransactionsServiceError",
    "LocationArchivedError",
    "LocationNotFoundError",
    "TransferLocationsError",
    "get",
    "list_transactions",
    "record",
    "record_transfer",
]
