"""Assembly-line backfill engine (epic #267 Phase 7a): derive Parts,
build product→part BOMs, re-point open jobs. Dry-run, idempotent,
reversible."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.job import Job
from app.models.part import Part
from app.models.product_bom_item import ProductBomItem
from app.services import materials as materials_service
from app.services import products as products_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.assembly_line_migration.framework import run_all
from scripts.assembly_line_migration.recipe import ORIGIN_KEY, ORIGIN_VALUE
from scripts.assembly_line_migration.reverse import reverse_all
from tests._jobs_helpers import insert_legacy_product_job


async def _owner_id(session: AsyncSession) -> uuid.UUID:
    user = await create_user(
        session,
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        password="pw",
        full_name="t",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    return user.id


def _plate(num: int, *, grams: dict[uuid.UUID, Decimal], pps: int = 1) -> dict:
    """A legacy plate spec for insert_legacy_product_job."""
    return {
        "name": "Bracket",
        "plate_number": num,
        "parts_per_set": pps,
        "print_minutes": 60,
        "grams": grams,
        "setup": 0,
    }


async def _seed(session: AsyncSession):
    """Two products. Product A: two single-plate jobs sharing one recipe
    (R1) → should dedupe to ONE part. Product B: one single-plate job with
    a different recipe (R2)."""
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
    prod_a = await products_service.create(
        session, name="Widget A", description=None, unit_price=Decimal("10"), actor_user_id=None
    )
    prod_b = await products_service.create(
        session, name="Widget B", description=None, unit_price=Decimal("20"), actor_user_id=None
    )
    await session.commit()
    owner_id = await _owner_id(session)

    r1 = {mat.id: Decimal("50")}
    r2 = {mat.id: Decimal("80")}
    # Product A, job 1 + job 2 share recipe R1.
    for _ in range(2):
        await insert_legacy_product_job(
            session,
            product_id=prod_a.id,
            actor_user_id=owner_id,
            plates=[_plate(1, grams=r1)],
        )
    # Product B, one job with recipe R2.
    await insert_legacy_product_job(
        session,
        product_id=prod_b.id,
        actor_user_id=owner_id,
        plates=[_plate(1, grams=r2)],
    )
    await session.commit()
    return prod_a, prod_b, mat


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed(app_session)
    before = len((await app_session.execute(select(Part))).scalars().all())

    result = await run_all(session=app_session, dry_run=True)
    assert result.ok, result.summary()
    # Plan reports 2 deduped parts...
    derive = next(r for r in result.results if r.context == "derive_parts")
    assert derive.rows_out == 2
    # ...but nothing was written.
    after = len((await app_session.execute(select(Part))).scalars().all())
    assert after == before


@pytest.mark.asyncio
async def test_commit_derives_dedupes_boms_and_repoints(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    prod_a, prod_b, _mat = await _seed(app_session)

    result = await run_all(session=app_session, dry_run=False)
    assert result.ok, result.summary()

    # Two distinct recipes → two PART-MIG parts (R1 deduped across 2 jobs).
    parts = list((await app_session.execute(select(Part))).scalars().all())
    mig = [p for p in parts if (p.custom_fields or {}).get(ORIGIN_KEY) == ORIGIN_VALUE]
    assert len(mig) == 2
    assert all(p.sku.startswith("PART-MIG-") for p in mig)

    # Product A has exactly one part BOM line; Product B one.
    a_lines = list(
        (
            await app_session.execute(
                select(ProductBomItem).where(
                    ProductBomItem.parent_product_id == prod_a.id,
                    ProductBomItem.component_kind == "part",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(a_lines) == 1
    assert a_lines[0].quantity == Decimal("1")
    b_lines = list(
        (
            await app_session.execute(
                select(ProductBomItem).where(
                    ProductBomItem.parent_product_id == prod_b.id,
                    ProductBomItem.component_kind == "part",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(b_lines) == 1

    # All three open jobs were re-pointed (product_id retained).
    jobs = list((await app_session.execute(select(Job))).scalars().all())
    assert len(jobs) == 3
    assert all(j.part_id is not None for j in jobs)
    assert all(j.product_id is not None for j in jobs)
    repoint = next(r for r in result.results if r.context == "repoint_jobs")
    assert repoint.rows_out == 3


@pytest.mark.asyncio
async def test_idempotent_rerun_skips(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed(app_session)
    await run_all(session=app_session, dry_run=False)
    parts_after_first = len((await app_session.execute(select(Part))).scalars().all())

    second = await run_all(session=app_session, dry_run=False)
    assert second.ok
    derive = next(r for r in second.results if r.context == "derive_parts")
    assert derive.rows_out == 0
    assert derive.rows_skipped == 2
    repoint = next(r for r in second.results if r.context == "repoint_jobs")
    assert repoint.rows_skipped == 3
    # No duplicate parts created.
    assert len((await app_session.execute(select(Part))).scalars().all()) == parts_after_first


@pytest.mark.asyncio
async def test_multi_plate_open_job_is_flagged_not_repointed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    mat = await materials_service.create(
        app_session,
        name=f"PLA {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await app_session.commit()
    prod = await products_service.create(
        session=app_session,
        name="Multi",
        description=None,
        unit_price=Decimal("5"),
        actor_user_id=None,
    )
    await app_session.commit()
    owner_id = await _owner_id(app_session)
    job = await insert_legacy_product_job(
        app_session,
        product_id=prod.id,
        actor_user_id=owner_id,
        plates=[
            _plate(1, grams={mat.id: Decimal("50")}),
            _plate(2, grams={mat.id: Decimal("80")}),
        ],
    )
    await app_session.commit()

    result = await run_all(session=app_session, dry_run=False)
    assert result.ok
    repoint = next(r for r in result.results if r.context == "repoint_jobs")
    assert any(str(job.id) in item for item in repoint.review_items)
    refreshed = (await app_session.execute(select(Job).where(Job.id == job.id))).scalar_one()
    assert refreshed.part_id is None  # not auto-repointed


@pytest.mark.asyncio
async def test_material_bom_line_flagged(client: AsyncClient, app_session: AsyncSession) -> None:
    prod_a, _prod_b, mat = await _seed(app_session)
    # Legacy direct-material BOM line on product A (covered by its part R1).
    app_session.add(
        ProductBomItem(
            id=uuid.uuid4(),
            parent_product_id=prod_a.id,
            component_kind="material",
            component_id=mat.id,
            quantity=Decimal("50"),
        )
    )
    await app_session.commit()

    result = await run_all(session=app_session, dry_run=False)
    boms = next(r for r in result.results if r.context == "product_boms")
    assert any("safe to remove" in item for item in boms.review_items)
    # Non-destructive: the material line is still present.
    still = list(
        (
            await app_session.execute(
                select(ProductBomItem).where(
                    ProductBomItem.parent_product_id == prod_a.id,
                    ProductBomItem.component_kind == "material",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(still) == 1


@pytest.mark.asyncio
async def test_reverse_undoes_commit(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed(app_session)
    await run_all(session=app_session, dry_run=False)
    assert len((await app_session.execute(select(Part))).scalars().all()) >= 2

    rev = await reverse_all(session=app_session, dry_run=False)
    assert rev.ok, rev.summary()
    assert rev.parts_deleted == 2

    # Migration parts + their BOM lines gone; jobs un-pointed.
    parts = list((await app_session.execute(select(Part))).scalars().all())
    assert [p for p in parts if (p.custom_fields or {}).get(ORIGIN_KEY) == ORIGIN_VALUE] == []
    part_lines = list(
        (
            await app_session.execute(
                select(ProductBomItem).where(ProductBomItem.component_kind == "part")
            )
        )
        .scalars()
        .all()
    )
    assert part_lines == []
    jobs = list((await app_session.execute(select(Job))).scalars().all())
    assert all(j.part_id is None for j in jobs)
