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
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import inventory_transactions as transactions_service
from app.services.materials import MaterialNotFoundError
from app.services.settings.service import SettingsService

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


class InventoryConfigError(MaterialReceiptsServiceError):
    """Receiving is enabled but no default location is configured.

    Surfaced when the ``inventory.default_receiving_location_id`` setting
    is unset AND no active ``workshop`` location exists to fall back to.
    Router maps to HTTP 400.
    """


async def _resolve_receiving_location_id(session: AsyncSession) -> uuid.UUID:
    """Pick a default location for a material receipt to land in.

    Resolution chain (Phase 3.2):

    1. ``inventory.default_receiving_location_id`` setting, if set.
    2. Otherwise, the lowest-code active ``workshop`` location (sorted
       alphanumerically by ``code``).
    3. Otherwise, raise :class:`InventoryConfigError`.

    The fallback exists so a fresh install with one workshop location
    "just works" without an explicit settings write.
    """
    configured: uuid.UUID | None = await SettingsService.get(
        "inventory.default_receiving_location_id", session=session
    )
    if configured is not None:
        # Validate the configured ID still resolves to an active location.
        stmt = select(InventoryLocation).where(InventoryLocation.id == configured)
        loc = (await session.execute(stmt)).scalar_one_or_none()
        if loc is not None and not loc.is_archived:
            return loc.id
        # Fall through to discovery — a stale setting shouldn't brick the receive flow.

    from sqlalchemy import asc

    stmt = (
        select(InventoryLocation)
        .where(InventoryLocation.kind == InventoryLocationKind.WORKSHOP)
        .where(InventoryLocation.is_archived.is_(False))
        .order_by(asc(InventoryLocation.code))
        .limit(1)
    )
    fallback = (await session.execute(stmt)).scalar_one_or_none()
    if fallback is None:
        raise InventoryConfigError(
            "no default receiving location: configure "
            "inventory.default_receiving_location_id or create a workshop location"
        )
    return fallback.id


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

    Also (Phase 3.2) records a parallel ``inventory_transaction`` row
    with ``kind='receipt'`` so the generic inventory stream sees the
    arrival, and emits a matching ``inventory.TransactionRecorded``
    event in the same transaction. The transaction lands at the
    configured ``inventory.default_receiving_location_id`` setting; if
    unset, falls back to the lowest-code active workshop location; if
    none exists, raises :class:`InventoryConfigError`.

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

    # Phase 3.3: emit the inventory_transaction (and its
    # TransactionRecorded event) FIRST so the on-hand projection has
    # already updated ``inventory_on_hand`` by the time the
    # ``inventory.MaterialReceived`` event below fires. The
    # ``material_cost`` projection reads the on-hand total to derive
    # ``old_on_hand`` (subtracting this receipt's grams), so this order
    # matters for live append; replay walks the events in the same
    # order, preserving parity.
    location_id = await _resolve_receiving_location_id(session)
    await transactions_service.record(
        session,
        kind="receipt",
        entity_kind="material",
        entity_id=material_id,
        location_id=location_id,
        quantity=grams,
        actor_user_id=actor_user_id,
        unit_cost=unit_cost,
        reason=reference,
    )

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
