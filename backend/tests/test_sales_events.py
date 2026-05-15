"""Sales event-type round-trip + audit projection wiring (Phase 6.2, #94).

Verifies all five sale-lifecycle events are registered, validate, render
to audit summaries, and produce excerpts that NEVER include
``customer_email`` or ``notes``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.events.registry import (
    InvalidEventPayloadError,
    is_registered,
    validate_payload,
)
from app.events.types import sales as sales_events
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary
from app.services import sales as sales_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_user


def test_all_five_event_types_are_registered() -> None:
    for t in (
        sales_events.TYPE_SALE_CREATED,
        sales_events.TYPE_SALE_UPDATED,
        sales_events.TYPE_SALE_CONFIRMED,
        sales_events.TYPE_SALE_FULFILLED,
        sales_events.TYPE_SALE_CANCELLED,
    ):
        assert is_registered(t), f"event type {t} should be registered"


def test_created_payload_round_trip() -> None:
    sid = uuid.uuid4()
    cid = uuid.uuid4()
    normalized = validate_payload(
        sales_events.TYPE_SALE_CREATED,
        {
            "sale_id": str(sid),
            "sale_number": "SO-2026-0001",
            "channel_id": str(cid),
            "external_order_id": "ETSY-12345",
            "customer_name": "Test",
            "customer_email": "x@example.com",
            "occurred_at": datetime.now(UTC).isoformat(),
            "subtotal": "10.000000",
            "discount_amount": "0.000000",
            "shipping_amount": "0.000000",
            "tax_amount": "0.000000",
            "channel_fee_amount": "0.000000",
            "total_amount": "10.000000",
            "state": "draft",
            "notes": None,
            "items": [],
        },
    )
    assert normalized["sale_number"] == "SO-2026-0001"


def test_created_payload_rejects_extra_field() -> None:
    with pytest.raises(InvalidEventPayloadError):
        validate_payload(
            sales_events.TYPE_SALE_CREATED,
            {
                "sale_id": str(uuid.uuid4()),
                "sale_number": "SO-2026-0001",
                "channel_id": str(uuid.uuid4()),
                "customer_name": "X",
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "subtotal": "0",
                "discount_amount": "0",
                "shipping_amount": "0",
                "tax_amount": "0",
                "channel_fee_amount": "0",
                "total_amount": "0",
                "state": "draft",
                "items": [],
                "surprise": "field",
            },
        )


def test_state_transition_payloads_round_trip() -> None:
    for t in (
        sales_events.TYPE_SALE_FULFILLED,
        sales_events.TYPE_SALE_CANCELLED,
    ):
        validate_payload(t, {"sale_id": str(uuid.uuid4()), "sale_number": "SO-2026-0001"})


def test_audit_summary_created_mentions_sale_number() -> None:
    msg = render_summary(
        sales_events.TYPE_SALE_CREATED,
        {
            "sale_id": str(uuid.uuid4()),
            "sale_number": "SO-2026-0042",
            "channel_id": str(uuid.uuid4()),
            "total_amount": "99.99",
        },
        actor_label="owner@example.com",
        aggregate_type="sale",
        aggregate_id="00000000-0000-0000-0000-000000000000",
    )
    assert "SO-2026-0042" in msg
    assert "owner@example.com" in msg


def test_audit_summary_state_transitions() -> None:
    for t, verb in (
        (sales_events.TYPE_SALE_CONFIRMED, "confirmed"),
        (sales_events.TYPE_SALE_FULFILLED, "fulfilled"),
        (sales_events.TYPE_SALE_CANCELLED, "cancelled"),
    ):
        payload = {"sale_id": str(uuid.uuid4()), "sale_number": "SO-2026-0099"}
        if t == sales_events.TYPE_SALE_CONFIRMED:
            payload["channel_id"] = str(uuid.uuid4())
            payload["total_amount"] = "1.00"
        msg = render_summary(
            t,
            payload,
            actor_label="owner@example.com",
            aggregate_type="sale",
            aggregate_id=payload["sale_id"],
        )
        assert verb in msg
        assert "SO-2026-0099" in msg


def test_audit_excerpt_created_strictly_whitelists() -> None:
    """``customer_email`` and ``notes`` MUST NEVER appear in the excerpt."""
    payload = {
        "sale_id": str(uuid.uuid4()),
        "sale_number": "SO-2026-0001",
        "channel_id": str(uuid.uuid4()),
        "customer_name": "PII Person",
        "customer_email": "pii@example.com",
        "total_amount": "55.55",
        "notes": "private operator note",
    }
    excerpt = compute_excerpt(sales_events.TYPE_SALE_CREATED, payload)
    assert excerpt is not None
    assert excerpt.get("sale_number") == "SO-2026-0001"
    assert "channel_id" in excerpt
    assert excerpt.get("total_amount") == "55.55"
    # PII guards.
    assert "customer_email" not in excerpt
    assert "customer_name" not in excerpt
    assert "notes" not in excerpt


def test_audit_excerpt_state_transitions_carry_minimal_fields() -> None:
    cid = str(uuid.uuid4())
    confirmed = compute_excerpt(
        sales_events.TYPE_SALE_CONFIRMED,
        {
            "sale_id": str(uuid.uuid4()),
            "sale_number": "SO-X",
            "channel_id": cid,
            "total_amount": "1",
        },
    )
    assert confirmed is not None
    assert confirmed["sale_number"] == "SO-X"
    assert "customer_email" not in confirmed

    fulfilled = compute_excerpt(
        sales_events.TYPE_SALE_FULFILLED,
        {"sale_id": str(uuid.uuid4()), "sale_number": "SO-X"},
    )
    assert fulfilled == {"sale_number": "SO-X"}


@pytest.mark.asyncio
async def test_events_flow_through_to_audit_log(app_session: AsyncSession) -> None:
    """End-to-end: confirm a sale → audit_log has SaleCreated + SaleConfirmed."""
    from app.models.audit import AuditLog
    from sqlalchemy import select

    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="Test",
        customer_email="test@example.com",
        occurred_at=datetime.now(UTC),
        notes="private note",
        items=[
            {
                "kind": "manual",
                "description": "Line",
                "quantity": "1",
                "unit_price": "1",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()

    rows = (
        (await app_session.execute(select(AuditLog).where(AuditLog.aggregate_id == sale.id)))
        .scalars()
        .all()
    )
    types = [r.event_type for r in rows]
    assert sales_events.TYPE_SALE_CREATED in types
    assert sales_events.TYPE_SALE_CONFIRMED in types

    # No excerpt for any sale event must mention customer_email or notes.
    for row in rows:
        if row.payload_excerpt is None:
            continue
        excerpt_str = str(row.payload_excerpt)
        assert "test@example.com" not in excerpt_str, row.event_type
        assert "private note" not in excerpt_str, row.event_type
