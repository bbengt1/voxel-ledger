"""Shipping event-type registration + audit projection wiring (Phase 6.6, #98).

Verifies all four shipping events are registered, validate, render to
summaries, and produce audit excerpts that NEVER include ``ship_to``,
``ship_from``, or ``label_pdf_storage_key`` (the PII / private fields
the spec forbids).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.events.registry import (
    InvalidEventPayloadError,
    is_registered,
    validate_payload,
)
from app.events.types import sales as sales_events
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary
from app.services import shipping as shipping_service
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._shipping_helpers import (
    SHIP_TO_FIXTURE,
    seed_draft_sale,
    seed_shipping_settings,
)

SHIPPING_EVENT_TYPES = (
    sales_events.TYPE_SHIPPING_LABEL_PURCHASED,
    sales_events.TYPE_SHIPMENT_SHIPPED,
    sales_events.TYPE_SHIPMENT_DELIVERED,
    sales_events.TYPE_SHIPMENT_CANCELLED,
)


def test_all_four_shipping_event_types_registered() -> None:
    for t in SHIPPING_EVENT_TYPES:
        assert is_registered(t), f"shipping event type {t} is not registered"


def test_label_purchased_payload_round_trip() -> None:
    sid = uuid.uuid4()
    saleid = uuid.uuid4()
    validate_payload(
        sales_events.TYPE_SHIPPING_LABEL_PURCHASED,
        {
            "shipment_id": str(sid),
            "sale_id": str(saleid),
            "carrier": "static_fallback",
            "service_level": "ground",
            "tracking_number": None,
            "tracking_url": None,
            "cost_amount": "0",
            "label_pdf_storage_key": f"shipping-labels/{sid}.pdf",
        },
    )


def test_label_purchased_payload_rejects_extra_field() -> None:
    with pytest.raises(InvalidEventPayloadError):
        validate_payload(
            sales_events.TYPE_SHIPPING_LABEL_PURCHASED,
            {
                "shipment_id": str(uuid.uuid4()),
                "sale_id": str(uuid.uuid4()),
                "carrier": "static_fallback",
                "cost_amount": "0",
                "naughty_extra": "should be rejected",
            },
        )


def test_audit_excerpt_never_includes_ship_to_or_storage_key() -> None:
    """Belt-and-suspenders check on the whitelist: regardless of how the
    payload is shaped, the excerpt must NOT carry PII (``ship_to``,
    ``ship_from``) nor the internal ``label_pdf_storage_key`` handle.
    """
    payload = {
        "shipment_id": str(uuid.uuid4()),
        "sale_id": str(uuid.uuid4()),
        "carrier": "static_fallback",
        "service_level": "ground",
        "tracking_number": "TEST-abc",
        "tracking_url": None,
        "cost_amount": "0",
        "label_pdf_storage_key": "shipping-labels/foo.pdf",
        # These wouldn't even be in the real payload but if a future
        # refactor adds them, the whitelist must keep them out.
        "ship_to": SHIP_TO_FIXTURE,
        "ship_from": {"name": "Shop"},
    }
    excerpt = compute_excerpt(sales_events.TYPE_SHIPPING_LABEL_PURCHASED, payload)
    assert excerpt is not None
    assert "ship_to" not in excerpt
    assert "ship_from" not in excerpt
    assert "label_pdf_storage_key" not in excerpt
    # And the fields that SHOULD be there are there.
    assert excerpt["carrier"] == "static_fallback"
    assert excerpt["tracking_number"] == "TEST-abc"


def test_audit_summaries_render_for_all_four_event_types() -> None:
    """Each event type has a custom summary formatter — confirm none
    falls through to the generic ``did X on Y:Z`` template."""
    payload = {
        "shipment_id": str(uuid.uuid4()),
        "sale_id": str(uuid.uuid4()),
        "carrier": "static_fallback",
        "tracking_number": None,
        "cost_amount": "0",
        "void_requested": False,
    }
    for t in SHIPPING_EVENT_TYPES:
        summary = render_summary(
            t,
            payload,
            actor_label="tester@example.com",
            aggregate_type="shipment",
            aggregate_id=payload["shipment_id"],
        )
        assert "did " not in summary, f"event type {t} fell through to the generic summary template"
        assert "tester@example.com" in summary


async def test_purchase_label_emits_event_into_event_log(
    app_session: AsyncSession,
) -> None:
    from app.models.event import Event

    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=250,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="stub",
        session=app_session,
    )
    await app_session.commit()
    # Use the stub so we can assert a tracking-number value.
    from app.services.shipping.carriers import StubCarrier

    shipment = await shipping_service.purchase_label(
        shipment.id, carrier_client=StubCarrier(), session=app_session
    )
    await app_session.commit()

    row = (
        await app_session.execute(
            select(Event)
            .where(Event.type == sales_events.TYPE_SHIPPING_LABEL_PURCHASED)
            .order_by(desc(Event.position))
            .limit(1)
        )
    ).scalar_one()
    assert row.payload["carrier"] == "stub"
    assert row.payload["tracking_number"].startswith("TEST-")
    assert Decimal(row.payload["cost_amount"]) == Decimal("9.99")
    # The PII / private handle land in the payload (events are full
    # source-of-truth), but they MUST be excluded by the projection
    # excerpt — covered above.
    assert "ship_to" not in row.payload
