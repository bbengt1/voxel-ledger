"""Materials service: create/update/archive/unarchive happy paths."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models import Base
from app.models.event import Event
from app.services import materials as materials_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_material_happy_path(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    m = await materials_service.create(
        session,
        name="Standard PLA",
        brand="Polymaker",
        material_type="PLA",
        color="black",
        density_g_per_cm3=Decimal("1.24"),
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await session.commit()

    assert m.id is not None
    assert m.name == "Standard PLA"
    assert m.brand == "Polymaker"
    assert m.material_type == "PLA"
    assert m.color == "black"
    assert m.density_g_per_cm3 == Decimal("1.24")
    assert m.current_cost_per_gram == Decimal("0")
    # Phase 3.3: on_hand_grams column removed; balance lives in inventory_on_hand.
    assert m.low_stock_threshold_grams is None
    assert m.is_archived is False

    # MaterialCreated event was emitted.
    events = (
        (await session.execute(select(Event).where(Event.type == "catalog.MaterialCreated")))
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["material_id"] == str(m.id)
    assert payload["name"] == "Standard PLA"


@pytest.mark.asyncio
async def test_create_duplicate_active_triple_rejected(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color="red",
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    with pytest.raises(materials_service.DuplicateMaterialError):
        await materials_service.create(
            session,
            name="PLA",
            brand="A",
            material_type="PLA",
            color="red",
            density_g_per_cm3=None,
            spool_weight_grams=Decimal("1000"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_update_emits_diff_payload(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    m = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color="red",
        density_g_per_cm3=Decimal("1.24"),
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await materials_service.update(
        session,
        material_id=m.id,
        patch={"name": "PLA Pro", "color": "blue"},
        actor_user_id=None,
    )
    await session.commit()

    events = (
        (
            await session.execute(
                select(Event)
                .where(Event.type == "catalog.MaterialUpdated")
                .order_by(Event.position)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["before"] == {"name": "PLA", "color": "red"}
    assert payload["after"] == {"name": "PLA Pro", "color": "blue"}


@pytest.mark.asyncio
async def test_update_noop_emits_nothing(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    m = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color="red",
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await materials_service.update(
        session,
        material_id=m.id,
        patch={"name": "PLA"},  # same value
        actor_user_id=None,
    )
    await session.commit()

    events = (
        (await session.execute(select(Event).where(Event.type == "catalog.MaterialUpdated")))
        .scalars()
        .all()
    )
    assert events == []


@pytest.mark.asyncio
async def test_archive_unarchive(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    m = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await materials_service.archive(session, material_id=m.id, actor_user_id=None)
    await session.commit()
    fresh = await materials_service.get(session, m.id)
    assert fresh.is_archived is True

    await materials_service.unarchive(session, material_id=m.id, actor_user_id=None)
    await session.commit()
    fresh = await materials_service.get(session, m.id)
    assert fresh.is_archived is False

    types = [
        e.type
        for e in (await session.execute(select(Event).order_by(Event.position))).scalars().all()
    ]
    assert "catalog.MaterialArchived" in types
    assert "catalog.MaterialUnarchived" in types


@pytest.mark.asyncio
async def test_unarchive_blocked_by_active_duplicate(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    m1 = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await materials_service.archive(session, material_id=m1.id, actor_user_id=None)
    # Create a fresh active triple with the same identifiers.
    await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    with pytest.raises(materials_service.DuplicateMaterialError):
        await materials_service.unarchive(session, material_id=m1.id, actor_user_id=None)


@pytest.mark.asyncio
async def test_list_pagination_and_search(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    for i, color in enumerate(["red", "green", "blue", "yellow"]):
        await materials_service.create(
            session,
            name=f"PLA {i}",
            brand="A",
            material_type="PLA",
            color=color,
            density_g_per_cm3=None,
            spool_weight_grams=Decimal("1000"),
            actor_user_id=None,
        )
    page = await materials_service.list_materials(session, limit=2)
    assert len(page.items) == 2
    assert page.next_cursor is not None

    page2 = await materials_service.list_materials(session, limit=2, cursor=page.next_cursor)
    assert len(page2.items) == 2

    # Search by color.
    page = await materials_service.list_materials(session, search="blue")
    assert {m.color for m in page.items} == {"blue"}


@pytest.mark.asyncio
async def test_get_not_found_raises(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    with pytest.raises(materials_service.MaterialNotFoundError):
        await materials_service.get(session, uuid.uuid4())
