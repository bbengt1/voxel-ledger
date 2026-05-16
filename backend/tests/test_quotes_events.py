"""Quote event-type registration + audit projection wiring (Phase 7.2, #110).

Verifies all 8 quote-lifecycle events are registered, validate, render
to audit summaries, and produce excerpts that NEVER include ``notes`` or
``billing_address_snapshot`` (PII).
"""

from __future__ import annotations

import uuid

import pytest
from app.events.registry import is_registered, validate_payload
from app.events.types import ar as ar_events
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary
from app.services import quotes as quotes_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._quotes_helpers import seed_customer, seed_user

ALL_TYPES = (
    ar_events.TYPE_QUOTE_CREATED,
    ar_events.TYPE_QUOTE_UPDATED,
    ar_events.TYPE_QUOTE_SENT,
    ar_events.TYPE_QUOTE_ACCEPTED,
    ar_events.TYPE_QUOTE_DECLINED,
    ar_events.TYPE_QUOTE_EXPIRED,
    ar_events.TYPE_QUOTE_CANCELLED,
    ar_events.TYPE_QUOTE_CONVERTED_TO_INVOICE,
)


def test_all_eight_event_types_are_registered() -> None:
    for t in ALL_TYPES:
        assert is_registered(t), f"event type {t} should be registered"


def test_created_payload_round_trip() -> None:
    qid = uuid.uuid4()
    cid = uuid.uuid4()
    normalized = validate_payload(
        ar_events.TYPE_QUOTE_CREATED,
        {
            "quote_id": str(qid),
            "quote_number": "QT-2026-0001",
            "customer_id": str(cid),
            "state": "draft",
            "issued_at": None,
            "valid_until": None,
            "subtotal": "10.000000",
            "discount_amount": "0.000000",
            "tax_amount": "0.000000",
            "total_amount": "10.000000",
            "notes": None,
            "billing_address_snapshot": None,
            "items": [],
        },
    )
    assert normalized["quote_number"] == "QT-2026-0001"


def test_state_transition_payloads_round_trip() -> None:
    qid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    # Sent / Accepted carry total_amount.
    validate_payload(
        ar_events.TYPE_QUOTE_SENT,
        {
            "quote_id": qid,
            "quote_number": "QT-X",
            "customer_id": cid,
            "total_amount": "1",
            "issued_at": "2026-01-01T00:00:00+00:00",
        },
    )
    validate_payload(
        ar_events.TYPE_QUOTE_ACCEPTED,
        {"quote_id": qid, "quote_number": "QT-X", "customer_id": cid, "total_amount": "1"},
    )
    for t in (
        ar_events.TYPE_QUOTE_DECLINED,
        ar_events.TYPE_QUOTE_EXPIRED,
        ar_events.TYPE_QUOTE_CANCELLED,
    ):
        validate_payload(t, {"quote_id": qid, "quote_number": "QT-X", "customer_id": cid})


def test_audit_summary_mentions_quote_number() -> None:
    msg = render_summary(
        ar_events.TYPE_QUOTE_CREATED,
        {
            "quote_id": str(uuid.uuid4()),
            "quote_number": "QT-2026-0042",
            "customer_id": str(uuid.uuid4()),
            "total_amount": "99.99",
        },
        actor_label="owner@example.com",
        aggregate_type="quote",
        aggregate_id="00000000-0000-0000-0000-000000000000",
    )
    assert "QT-2026-0042" in msg
    assert "owner@example.com" in msg


def test_audit_excerpt_strictly_whitelists() -> None:
    """``notes`` and ``billing_address_snapshot`` MUST NEVER appear."""
    payload = {
        "quote_id": str(uuid.uuid4()),
        "quote_number": "QT-2026-0001",
        "customer_id": str(uuid.uuid4()),
        "total_amount": "55.55",
        "notes": "private operator note",
        "billing_address_snapshot": {"line1": "secret street"},
    }
    excerpt = compute_excerpt(ar_events.TYPE_QUOTE_CREATED, payload)
    assert excerpt is not None
    assert excerpt.get("quote_number") == "QT-2026-0001"
    assert excerpt.get("total_amount") == "55.55"
    assert "customer_id" in excerpt
    # PII guards.
    assert "notes" not in excerpt
    assert "billing_address_snapshot" not in excerpt


@pytest.mark.asyncio
async def test_events_flow_through_to_audit_log(app_session: AsyncSession) -> None:
    """End-to-end: send + accept a quote → audit_log has all 3 events
    and no excerpt mentions ``notes`` or the billing address."""
    from app.models.audit import AuditLog
    from sqlalchemy import select

    user = await seed_user(app_session)
    customer = await seed_customer(
        app_session,
        billing_address={"line1": "secret street 1", "city": "secret town"},
    )

    quote = await quotes_service.create_draft(
        app_session,
        customer_id=customer.id,
        notes="private operator note",
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

    await quotes_service.send(app_session, quote_id=quote.id, actor_user_id=user.id)
    await app_session.commit()

    await quotes_service.accept(app_session, quote_id=quote.id, actor_user_id=user.id)
    await app_session.commit()

    rows = (
        (await app_session.execute(select(AuditLog).where(AuditLog.aggregate_id == quote.id)))
        .scalars()
        .all()
    )
    types = [r.event_type for r in rows]
    assert ar_events.TYPE_QUOTE_CREATED in types
    assert ar_events.TYPE_QUOTE_SENT in types
    assert ar_events.TYPE_QUOTE_ACCEPTED in types

    for row in rows:
        if row.payload_excerpt is None:
            continue
        excerpt_str = str(row.payload_excerpt)
        assert "private operator note" not in excerpt_str, row.event_type
        assert "secret street" not in excerpt_str, row.event_type
        assert "secret town" not in excerpt_str, row.event_type
