"""Projection: per-(entity, location) on-hand running balance.

Subscribes to ``inventory.TransactionRecorded``. For every transaction
the projection upserts a single row in ``inventory_on_hand`` keyed by
``(entity_kind, entity_id, location_id)`` and accumulates the signed
quantity. Transfers — which emit two TransactionRecorded events,
one ``transfer_out`` and one ``transfer_in`` with opposite signs — land
as two separate upserts that touch two different rows atomically inside
the caller's transaction.

Read-after-write invariant
--------------------------
Live projection runs inside the same DB transaction as
``EventStore.append``. After the append commits, the ``inventory_on_hand``
row reflects the new running sum. Downstream queries see consistent
state without any eventual-consistency window.

Dispatch ordering
-----------------
The ``material_cost`` projection's weighted-average formula needs the
PRIOR on-hand value. Both this handler and ``material_cost`` see
**different** events (TransactionRecorded vs MaterialReceived), but the
receipts service appends ``inventory.MaterialReceived`` first, then the
parallel ``inventory.TransactionRecorded``. The material_cost handler
therefore reads the prior (pre-receipt) sum from ``inventory_on_hand``
when it computes the new weighted average. Replay honors the same
event-log ordering, so parity holds.

Idempotency
-----------
Replay against a freshly-truncated ``inventory_on_hand`` reproduces the
same totals because INSERT ... ON CONFLICT DO UPDATE with sum semantics
is associative and commutative on integer/decimal deltas. The order
events arrive doesn't change the final sum.

TODO(phase-3.4): emit an ``inventory.LowStockCrossed`` event when an
update pushes ``on_hand`` below the configured threshold.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.inventory import TYPE_TRANSACTION_RECORDED
from app.models.event import Event
from app.models.inventory_on_hand import InventoryOnHand
from app.projections.registry import projection

HANDLER_NAME = "inventory_on_hand"
READ_MODEL_TABLES: tuple[str, ...] = ("inventory_on_hand",)

_QUANTUM = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


@projection(
    event_type=TYPE_TRANSACTION_RECORDED,
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_inventory_on_hand(event: Event, session: AsyncSession) -> None:
    """Apply one ``inventory.TransactionRecorded`` event.

    Uses dialect-specific ``INSERT ... ON CONFLICT DO UPDATE`` so the
    create-or-accumulate is a single round trip. SQLite (test path) and
    Postgres (prod) both support it. SQLAlchemy core handles the Uuid /
    Numeric type binding correctly so we don't have to hand-coerce.
    """
    payload = event.payload or {}
    delta = _to_decimal(payload["signed_quantity"]).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert

    values = {
        "id": uuid.uuid4(),
        "entity_kind": payload["entity_kind"],
        "entity_id": _to_uuid(payload["entity_id"]),
        "location_id": _to_uuid(payload["location_id"]),
        "on_hand": delta,
    }
    stmt = insert_fn(InventoryOnHand).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["entity_kind", "entity_id", "location_id"],
        set_={"on_hand": InventoryOnHand.on_hand + stmt.excluded.on_hand},
    )
    await session.execute(stmt)
    await session.flush()
