"""Shipment state machine (Phase 6.6, #98).

Happy-path: pending -> label_purchased -> shipped -> delivered.
Sad-path: every out-of-order transition raises
``InvalidShipmentStateError``.
"""

from __future__ import annotations

import pytest
from app.models.shipment import ShipmentState
from app.services import shipping as shipping_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._shipping_helpers import (
    SHIP_TO_FIXTURE,
    seed_draft_sale,
    seed_shipping_settings,
)


async def _new_shipment(session: AsyncSession):
    await seed_shipping_settings(session)
    sale = await seed_draft_sale(session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=100,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="static_fallback",
        session=session,
    )
    await session.commit()
    return shipment


async def test_happy_path_pending_to_delivered(app_session: AsyncSession) -> None:
    shipment = await _new_shipment(app_session)
    assert shipment.state == ShipmentState.PENDING

    shipment = await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()
    assert shipment.state == ShipmentState.LABEL_PURCHASED

    shipment = await shipping_service.mark_shipped(shipment.id, session=app_session)
    await app_session.commit()
    assert shipment.state == ShipmentState.SHIPPED

    shipment = await shipping_service.mark_delivered(shipment.id, session=app_session)
    await app_session.commit()
    assert shipment.state == ShipmentState.DELIVERED


async def test_cannot_mark_shipped_before_label_purchased(
    app_session: AsyncSession,
) -> None:
    shipment = await _new_shipment(app_session)
    with pytest.raises(shipping_service.InvalidShipmentStateError):
        await shipping_service.mark_shipped(shipment.id, session=app_session)


async def test_cannot_mark_delivered_before_shipped(
    app_session: AsyncSession,
) -> None:
    shipment = await _new_shipment(app_session)
    await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()
    with pytest.raises(shipping_service.InvalidShipmentStateError):
        await shipping_service.mark_delivered(shipment.id, session=app_session)


async def test_cannot_purchase_label_twice(app_session: AsyncSession) -> None:
    shipment = await _new_shipment(app_session)
    await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()
    with pytest.raises(shipping_service.InvalidShipmentStateError):
        await shipping_service.purchase_label(shipment.id, session=app_session)


async def test_cancel_from_pending_marks_no_void_requested(
    app_session: AsyncSession,
) -> None:
    """Cancelling a pending shipment shouldn't ask the carrier to void
    anything — no label exists yet."""
    from app.events.types import sales as sales_events
    from app.models.event import Event
    from sqlalchemy import desc, select

    shipment = await _new_shipment(app_session)
    await shipping_service.cancel(shipment.id, session=app_session)
    await app_session.commit()

    row = (
        await app_session.execute(
            select(Event)
            .where(Event.type == sales_events.TYPE_SHIPMENT_CANCELLED)
            .order_by(desc(Event.position))
            .limit(1)
        )
    ).scalar_one()
    assert row.payload["void_requested"] is False


async def test_cancel_after_label_marks_void_requested(
    app_session: AsyncSession,
) -> None:
    from app.events.types import sales as sales_events
    from app.models.event import Event
    from sqlalchemy import desc, select

    shipment = await _new_shipment(app_session)
    await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()

    await shipping_service.cancel(shipment.id, session=app_session)
    await app_session.commit()

    row = (
        await app_session.execute(
            select(Event)
            .where(Event.type == sales_events.TYPE_SHIPMENT_CANCELLED)
            .order_by(desc(Event.position))
            .limit(1)
        )
    ).scalar_one()
    assert row.payload["void_requested"] is True


async def test_terminal_states_cannot_transition_further(
    app_session: AsyncSession,
) -> None:
    shipment = await _new_shipment(app_session)
    await shipping_service.cancel(shipment.id, session=app_session)
    await app_session.commit()
    # Cancelled is terminal.
    with pytest.raises(shipping_service.InvalidShipmentStateError):
        await shipping_service.mark_shipped(shipment.id, session=app_session)
