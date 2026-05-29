"""Audit projection surfaces inventory.TransactionRecorded events."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.events.types import inventory as inventory_events
from app.models import Base
from app.models.audit import AuditLog
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def test_excerpt_whitelist_drops_cost() -> None:
    payload = {
        "kind": "receipt",
        "entity_kind": "material",
        "entity_id": "abc",
        "location_id": "xyz",
        "signed_quantity": "100",
        "unit_cost": "0.05",
        "total_cost": "5.00",
        "reason": "INV-1",
    }
    excerpt = compute_excerpt(inventory_events.TYPE_TRANSACTION_RECORDED, payload)
    assert excerpt == {
        "kind": "receipt",
        "entity_kind": "material",
        "entity_id": "abc",
        "location_id": "xyz",
        "signed_quantity": "100",
        "reason": "INV-1",
    }
    assert "unit_cost" not in excerpt
    assert "total_cost" not in excerpt


def test_summary_renders_concise_line() -> None:
    out = render_summary(
        inventory_events.TYPE_TRANSACTION_RECORDED,
        {
            "kind": "production_in",
            "entity_kind": "material",
            "entity_id": "m-1",
            "location_id": "l-1",
            "signed_quantity": "50",
        },
        actor_label="owner@x",
        aggregate_type="inventory_transaction",
        aggregate_id="t-1",
    )
    assert "production_in" in out
    assert "50" in out
    assert "material:m-1" in out


@pytest.mark.asyncio
async def test_audit_row_written_for_recorded_transaction(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await locations_service.create(
        session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await transactions_service.record(
        session,
        kind="production_in",
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("12"),
        actor_user_id=None,
    )
    await session.commit()

    rows = (
        (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.event_type == inventory_events.TYPE_TRANSACTION_RECORDED
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].payload_excerpt is not None
    # Unit/total cost must not have leaked into the excerpt.
    assert "unit_cost" not in rows[0].payload_excerpt
    assert "total_cost" not in rows[0].payload_excerpt
    assert "production_in" in rows[0].summary
