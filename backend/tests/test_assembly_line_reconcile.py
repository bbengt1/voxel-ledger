"""Reconciliation gate for the assembly-line backfill (epic #267 Phase 7b):
on-hand parity is a hard invariant; cost moves are soft."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.inventory_on_hand import InventoryOnHand
from app.services import materials as materials_service
from app.services import products as products_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.assembly_line_migration.framework import run_all
from scripts.assembly_line_migration.reconcile import capture, reconcile
from tests._jobs_helpers import insert_legacy_product_job


async def _seed(session: AsyncSession, location_id: uuid.UUID):
    mat = await materials_service.create(
        session,
        name=f"PLA {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await session.commit()
    prod = await products_service.create(
        session, name="Widget", description=None, unit_price=Decimal("10"), actor_user_id=None
    )
    await session.commit()
    user = await create_user(
        session,
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        password="pw",
        full_name="t",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    await insert_legacy_product_job(
        session,
        product_id=prod.id,
        actor_user_id=user.id,
        plates=[
            {
                "name": "Bracket",
                "plate_number": 1,
                "parts_per_set": 1,
                "print_minutes": 60,
                "grams": {mat.id: Decimal("50")},
                "setup": 0,
            }
        ],
    )
    # A product on-hand balance whose parity we assert across the backfill.
    session.add(
        InventoryOnHand(
            id=uuid.uuid4(),
            entity_kind="product",
            entity_id=prod.id,
            location_id=location_id,
            on_hand=Decimal("5"),
        )
    )
    await session.commit()
    return prod


@pytest.mark.asyncio
async def test_reconcile_passes_when_onhand_unchanged(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    await _seed(app_session, workshop_location.id)

    baseline = await capture(app_session)
    await run_all(session=app_session, dry_run=False)  # commit
    report = await reconcile(app_session, baseline)

    # Backfill writes no inventory → on-hand parity holds → PASS.
    assert report.ok, report.summary()
    assert report.hard_failures == []
    # Product gained a part BOM → cost moved → surfaced as a soft diff.
    assert any("cost" in d or "->" in d for d in report.cost_diffs)


@pytest.mark.asyncio
async def test_reconcile_hard_fails_on_onhand_drift(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    prod = await _seed(app_session, workshop_location.id)

    baseline = await capture(app_session)

    # Simulate stock drift (something a migration must never cause).
    row = (
        await app_session.execute(
            InventoryOnHand.__table__.select().where(
                (InventoryOnHand.entity_kind == "product") & (InventoryOnHand.entity_id == prod.id)
            )
        )
    ).first()
    assert row is not None
    await app_session.execute(
        InventoryOnHand.__table__.update()
        .where(InventoryOnHand.entity_id == prod.id)
        .values(on_hand=Decimal("4"))
    )
    await app_session.commit()

    report = await reconcile(app_session, baseline)
    assert not report.ok
    assert any("on-hand changed" in h for h in report.hard_failures)
