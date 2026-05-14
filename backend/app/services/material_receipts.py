"""Material-receipt service (Phase 2.1).

A receipt records grams + total cost arriving into inventory. The
service writes the receipt row, emits
``inventory.MaterialReceived``, and the ``material_cost`` projection
(synchronously, same transaction) updates the parent material's
``current_cost_per_gram`` and ``on_hand_grams``.

Decimal arithmetic only. ``unit_cost_at_receipt = total_cost / grams``
is computed here and stored alongside the receipt so historical pricing
is preserved if the parent material is later corrected.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import inventory as inventory_events
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.materials import MaterialNotFoundError

# Quantize unit_cost_at_receipt at storage time. The projection quantizes
# again for the running weighted average; both use 6 places, matching the
# Numeric(18, 6) column precision.
_UNIT_COST_QUANTUM = Decimal("0.000001")


class MaterialReceiptsServiceError(Exception):
    pass


class InvalidGramsError(MaterialReceiptsServiceError):
    pass


class InvalidTotalCostError(MaterialReceiptsServiceError):
    pass


class InvalidCursorError(MaterialReceiptsServiceError):
    pass


def _encode_cursor(received_at: datetime, receipt_id: uuid.UUID) -> str:
    raw = json.dumps({"r": received_at.isoformat(), "i": str(receipt_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["r"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def record(
    session: AsyncSession,
    *,
    material_id: uuid.UUID,
    grams: Decimal,
    total_cost: Decimal,
    vendor: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> MaterialReceipt:
    """Insert one receipt and emit ``inventory.MaterialReceived``.

    Validates grams > 0 and total_cost >= 0 at the service boundary in
    addition to the DB CHECK constraints. Computes
    ``unit_cost_at_receipt = total_cost / grams`` with Decimal precision
    and quantizes to six places.
    """
    if not isinstance(grams, Decimal):
        grams = Decimal(str(grams))
    if not isinstance(total_cost, Decimal):
        total_cost = Decimal(str(total_cost))

    if grams <= 0:
        raise InvalidGramsError("grams must be > 0")
    if total_cost < 0:
        raise InvalidTotalCostError("total_cost must be >= 0")

    # Ensure the parent exists. We need it inside the same transaction so
    # the projection's later UPDATE picks up our row.
    material = (
        await session.execute(select(Material).where(Material.id == material_id))
    ).scalar_one_or_none()
    if material is None:
        raise MaterialNotFoundError(str(material_id))

    unit_cost = (total_cost / grams).quantize(_UNIT_COST_QUANTUM, rounding=ROUND_HALF_UP)

    receipt = MaterialReceipt(
        material_id=material_id,
        received_at=datetime.now(UTC),
        grams=grams,
        total_cost=total_cost,
        unit_cost_at_receipt=unit_cost,
        vendor=vendor,
        reference=reference,
        notes=notes,
    )
    session.add(receipt)
    await session.flush()

    payload: dict[str, Any] = {
        "material_id": str(material_id),
        "grams": str(grams),
        "total_cost": str(total_cost),
        "unit_cost_at_receipt": str(unit_cost),
        "vendor": vendor,
        "reference": reference,
    }

    await event_store.append(
        EventCreate(
            type=inventory_events.TYPE_MATERIAL_RECEIVED,
            aggregate_type=inventory_events.AGGREGATE_TYPE,
            aggregate_id=material_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )
    return receipt


@dataclass
class ReceiptPage:
    items: list[MaterialReceipt]
    next_cursor: str | None


async def list_for_material(
    session: AsyncSession,
    *,
    material_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 50,
) -> ReceiptPage:
    stmt = select(MaterialReceipt).where(MaterialReceipt.material_id == material_id)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                MaterialReceipt.received_at < anchor_ts,
                and_(
                    MaterialReceipt.received_at == anchor_ts,
                    MaterialReceipt.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(MaterialReceipt.received_at), desc(MaterialReceipt.id)).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].received_at, rows[-1].id) if (rows and has_more) else None
    return ReceiptPage(items=rows, next_cursor=next_cursor)
