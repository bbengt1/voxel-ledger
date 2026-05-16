"""Shipping service (Phase 6.6, #98).

Owns the ``shipment`` aggregate. Wires through the carrier abstraction
in :mod:`.carriers` for label purchase + tracking and to local-FS
storage in :mod:`.storage` for the PDF blob.

State machine
-------------

    pending          -> label_purchased (purchase_label)
    label_purchased  -> shipped         (mark_shipped)
    shipped          -> delivered       (mark_delivered)
    (any)            -> cancelled       (cancel)
    delivered        -> returned        (out of scope for this phase)

Out-of-order transitions raise :class:`InvalidShipmentStateError`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import sales as sales_events
from app.models.sale import Sale
from app.models.shipment import Shipment, ShipmentState
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.settings.service import SettingsService
from app.services.shipping import storage as label_storage
from app.services.shipping.carriers import (
    CarrierClient,
    CarrierLabelResult,
    get_carrier_client,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ShippingServiceError(Exception):
    """Base. Routers map to 400 unless a more specific subclass matches."""


class ShipmentNotFoundError(ShippingServiceError):
    """Mapped to 404."""


class InvalidShipmentStateError(ShippingServiceError):
    """Out-of-order state transition rejected."""


class LabelNotAvailableError(ShippingServiceError):
    """The shipment has no stored label PDF (mapped to 404)."""


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_TRANSITIONS: dict[ShipmentState, frozenset[ShipmentState]] = {
    ShipmentState.PENDING: frozenset({ShipmentState.LABEL_PURCHASED, ShipmentState.CANCELLED}),
    ShipmentState.LABEL_PURCHASED: frozenset({ShipmentState.SHIPPED, ShipmentState.CANCELLED}),
    ShipmentState.SHIPPED: frozenset({ShipmentState.DELIVERED, ShipmentState.CANCELLED}),
    ShipmentState.DELIVERED: frozenset({ShipmentState.RETURNED}),
    ShipmentState.RETURNED: frozenset(),
    ShipmentState.CANCELLED: frozenset(),
}


def _ensure_transition(current: ShipmentState, target: ShipmentState) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidShipmentStateError(
            f"cannot transition shipment from {current.value} to {target.value}"
        )


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
            aggregate_type=sales_events.AGGREGATE_TYPE_SHIPMENT,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Internal lookups
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, shipment_id: uuid.UUID) -> Shipment:
    row = (
        await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    ).scalar_one_or_none()
    if row is None:
        raise ShipmentNotFoundError(str(shipment_id))
    return row


async def _load_sale(session: AsyncSession, sale_id: uuid.UUID) -> Sale:
    row = (await session.execute(select(Sale).where(Sale.id == sale_id))).scalar_one_or_none()
    if row is None:
        raise ShippingServiceError(f"sale {sale_id} not found")
    return row


async def _resolve_ship_from(session: AsyncSession) -> dict[str, Any]:
    raw = await SettingsService.get("shipping.ship_from_address", session=session)
    if not isinstance(raw, dict):
        raise ShippingServiceError("shipping.ship_from_address is not a dict")
    return dict(raw)


async def _resolve_default_carrier(session: AsyncSession) -> str:
    raw = await SettingsService.get("shipping.default_carrier", session=session)
    return str(raw or "static_fallback")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, shipment_id: uuid.UUID) -> Shipment:
    return await _load(session, shipment_id)


async def list_for_sale(session: AsyncSession, sale_id: uuid.UUID) -> list[Shipment]:
    rows = (
        (
            await session.execute(
                select(Shipment).where(Shipment.sale_id == sale_id).order_by(Shipment.created_at)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@dataclass
class CreateShipmentInput:
    ship_to: dict[str, Any]
    weight_grams: int | None = None
    dimensions_cm: dict[str, Any] | None = None
    service_level: str | None = None
    carrier_hint: str | None = None


async def create_shipment(
    sale_id: uuid.UUID,
    *,
    ship_to: dict[str, Any],
    weight_grams: int | None = None,
    dimensions_cm: dict[str, Any] | None = None,
    service_level: str | None = None,
    carrier_hint: str | None = None,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> Shipment:
    """Create a new ``pending`` shipment against ``sale_id``.

    The carrier slug is recorded eagerly (either the hint or the
    configured default) so the audit trail knows the intent even before
    a label is purchased. ``ship_from`` is snapshotted from settings at
    create time.
    """
    sale = await _load_sale(session, sale_id)
    ship_from = await _resolve_ship_from(session)
    carrier_name = carrier_hint or await _resolve_default_carrier(session)

    shipment = Shipment(
        sale_id=sale.id,
        state=ShipmentState.PENDING,
        carrier=carrier_name,
        service_level=service_level,
        weight_grams=weight_grams,
        dimensions_cm=dimensions_cm,
        ship_from=ship_from,
        ship_to=ship_to,
        cost_amount=Decimal("0"),
    )
    session.add(shipment)
    await session.flush()
    # No event on creation — the spec only registers four shipment
    # events (LabelPurchased / Shipped / Delivered / Cancelled). The
    # shipment becomes audit-visible the first time it transitions.
    _ = actor_user_id  # currently unused, reserved for future audit
    return shipment


async def purchase_label(
    shipment_id: uuid.UUID,
    *,
    carrier_client: CarrierClient | None = None,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> Shipment:
    """Buy (or render) a label for the shipment and persist it.

    Flow:
      1. Verify state is ``pending``.
      2. Invoke the carrier client (factory-resolved or caller-supplied).
      3. Persist the PDF under ``shipping-labels/{shipment_id}.pdf``.
      4. Update the shipment row with the carrier metadata + new state.
      5. Emit ``sales.ShippingLabelPurchased``.

    ``carrier_client`` is exposed so tests can inject :class:`StubCarrier`
    or a mock without having to mutate the settings; production code
    leaves it ``None`` and lets the factory pick.
    """
    shipment = await _load(session, shipment_id)
    _ensure_transition(shipment.state, ShipmentState.LABEL_PURCHASED)

    if carrier_client is None:
        carrier_client = get_carrier_client(shipment.carrier)

    result: CarrierLabelResult = carrier_client.purchase_label(
        ship_from=shipment.ship_from,
        ship_to=shipment.ship_to,
        weight_grams=shipment.weight_grams,
        dimensions_cm=shipment.dimensions_cm,
        service_level=shipment.service_level,
    )

    storage_key = label_storage.label_storage_key(shipment.id)
    await label_storage.write_label_pdf(result.pdf_bytes, storage_key=storage_key, session=session)

    shipment.carrier = result.carrier
    shipment.tracking_number = result.tracking_number
    shipment.tracking_url = result.tracking_url
    shipment.cost_amount = result.cost_amount
    shipment.label_pdf_storage_key = storage_key
    shipment.state = ShipmentState.LABEL_PURCHASED
    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_SHIPPING_LABEL_PURCHASED,
        aggregate_id=shipment.id,
        payload={
            "shipment_id": shipment.id,
            "sale_id": shipment.sale_id,
            "carrier": result.carrier,
            "service_level": shipment.service_level,
            "tracking_number": result.tracking_number,
            "tracking_url": result.tracking_url,
            "cost_amount": str(result.cost_amount),
            "label_pdf_storage_key": storage_key,
        },
        actor_user_id=actor_user_id,
    )
    return shipment


async def mark_shipped(
    shipment_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> Shipment:
    shipment = await _load(session, shipment_id)
    _ensure_transition(shipment.state, ShipmentState.SHIPPED)
    shipment.state = ShipmentState.SHIPPED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SHIPMENT_SHIPPED,
        aggregate_id=shipment.id,
        payload={
            "shipment_id": shipment.id,
            "sale_id": shipment.sale_id,
            "carrier": shipment.carrier,
            "tracking_number": shipment.tracking_number,
        },
        actor_user_id=actor_user_id,
    )
    return shipment


async def mark_delivered(
    shipment_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> Shipment:
    shipment = await _load(session, shipment_id)
    _ensure_transition(shipment.state, ShipmentState.DELIVERED)
    shipment.state = ShipmentState.DELIVERED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SHIPMENT_DELIVERED,
        aggregate_id=shipment.id,
        payload={
            "shipment_id": shipment.id,
            "sale_id": shipment.sale_id,
            "carrier": shipment.carrier,
            "tracking_number": shipment.tracking_number,
        },
        actor_user_id=actor_user_id,
    )
    return shipment


async def cancel(
    shipment_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> Shipment:
    """Cancel the shipment.

    If a label had already been purchased we flag ``void_requested=True``
    in the event payload so a future real-carrier integration can pick
    up the void asynchronously. The static fallback no-ops the void —
    there's no remote object to release.
    """
    shipment = await _load(session, shipment_id)
    _ensure_transition(shipment.state, ShipmentState.CANCELLED)
    had_label = shipment.label_pdf_storage_key is not None
    shipment.state = ShipmentState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SHIPMENT_CANCELLED,
        aggregate_id=shipment.id,
        payload={
            "shipment_id": shipment.id,
            "sale_id": shipment.sale_id,
            "carrier": shipment.carrier,
            "void_requested": had_label,
        },
        actor_user_id=actor_user_id,
    )
    return shipment


async def load_label_pdf(
    shipment_id: uuid.UUID,
    *,
    session: AsyncSession,
) -> bytes:
    """Read the stored label PDF for ``shipment_id``.

    Raises :class:`ShipmentNotFoundError` when the shipment doesn't
    exist, :class:`LabelNotAvailableError` when the shipment has no
    storage key or the bytes aren't on disk.
    """
    shipment = await _load(session, shipment_id)
    if not shipment.label_pdf_storage_key:
        raise LabelNotAvailableError("shipment has no label")
    pdf_bytes = await label_storage.read_label_pdf(shipment.label_pdf_storage_key, session=session)
    if pdf_bytes is None:
        raise LabelNotAvailableError("stored label is missing on disk")
    return pdf_bytes


__all__ = [
    "CreateShipmentInput",
    "InvalidShipmentStateError",
    "LabelNotAvailableError",
    "ShipmentNotFoundError",
    "ShippingServiceError",
    "cancel",
    "create_shipment",
    "get",
    "list_for_sale",
    "load_label_pdf",
    "mark_delivered",
    "mark_shipped",
    "purchase_label",
]
