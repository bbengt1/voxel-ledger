"""Inventory locations service: create/update/archive/unarchive paths."""

from __future__ import annotations

import uuid

import pytest
from app.models import Base
from app.models.event import Event
from app.models.inventory_location import InventoryLocationKind
from app.services import inventory_locations as locations_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_happy_path(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    loc = await locations_service.create(
        session,
        name="Workshop bench",
        code="WSB",
        kind="workshop",
        description="Main bench",
        actor_user_id=None,
    )
    await session.commit()

    assert loc.id is not None
    assert loc.name == "Workshop bench"
    assert loc.code == "WSB"
    assert loc.kind == InventoryLocationKind.WORKSHOP
    assert loc.is_archived is False

    events = (
        (await session.execute(select(Event).where(Event.type == "inventory.LocationCreated")))
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["location_id"] == str(loc.id)
    assert payload["code"] == "WSB"
    assert payload["kind"] == "workshop"


@pytest.mark.asyncio
async def test_create_duplicate_active_code_rejected(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await locations_service.create(
        session,
        name="One",
        code="DUP",
        kind="workshop",
        actor_user_id=None,
    )
    with pytest.raises(locations_service.DuplicateInventoryLocationError):
        await locations_service.create(
            session,
            name="Two",
            code="DUP",
            kind="staging",
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_update_emits_diff_payload(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    loc = await locations_service.create(
        session,
        name="Bench",
        code="BNC",
        kind="workshop",
        actor_user_id=None,
    )
    await locations_service.update(
        session,
        location_id=loc.id,
        patch={"name": "Bench (main)", "kind": "staging"},
        actor_user_id=None,
    )
    await session.commit()

    events = (
        (
            await session.execute(
                select(Event)
                .where(Event.type == "inventory.LocationUpdated")
                .order_by(Event.position)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["before"] == {"name": "Bench", "kind": "workshop"}
    assert payload["after"] == {"name": "Bench (main)", "kind": "staging"}


@pytest.mark.asyncio
async def test_update_noop_emits_nothing(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await locations_service.create(
        session,
        name="Bench",
        code="BNC",
        kind="workshop",
        actor_user_id=None,
    )
    await locations_service.update(
        session,
        location_id=loc.id,
        patch={"name": "Bench"},
        actor_user_id=None,
    )
    await session.commit()
    events = (
        (await session.execute(select(Event).where(Event.type == "inventory.LocationUpdated")))
        .scalars()
        .all()
    )
    assert events == []


@pytest.mark.asyncio
async def test_archive_unarchive(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await locations_service.create(
        session,
        name="Bench",
        code="BNC",
        kind="workshop",
        actor_user_id=None,
    )
    await locations_service.archive(session, location_id=loc.id, actor_user_id=None)
    await session.commit()
    fresh = await locations_service.get(session, loc.id)
    assert fresh.is_archived is True

    await locations_service.unarchive(session, location_id=loc.id, actor_user_id=None)
    await session.commit()
    fresh = await locations_service.get(session, loc.id)
    assert fresh.is_archived is False

    types = [
        e.type
        for e in (await session.execute(select(Event).order_by(Event.position))).scalars().all()
    ]
    assert "inventory.LocationArchived" in types
    assert "inventory.LocationUnarchived" in types


@pytest.mark.asyncio
async def test_unarchive_blocked_by_active_duplicate(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    first = await locations_service.create(
        session, name="One", code="DUP", kind="workshop", actor_user_id=None
    )
    await locations_service.archive(session, location_id=first.id, actor_user_id=None)
    await locations_service.create(
        session, name="Two", code="DUP", kind="staging", actor_user_id=None
    )
    with pytest.raises(locations_service.DuplicateInventoryLocationError):
        await locations_service.unarchive(session, location_id=first.id, actor_user_id=None)


@pytest.mark.asyncio
async def test_list_pagination_and_search(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for code in ["A", "B", "C", "D"]:
        await locations_service.create(
            session,
            name=f"Loc {code}",
            code=code,
            kind="virtual",
            actor_user_id=None,
        )
    page = await locations_service.list_locations(session, limit=2)
    assert len(page.items) == 2
    assert page.next_cursor is not None
    page2 = await locations_service.list_locations(session, limit=2, cursor=page.next_cursor)
    assert len(page2.items) == 2

    page = await locations_service.list_locations(session, search="Loc A")
    assert [loc.code for loc in page.items] == ["A"]

    page = await locations_service.list_locations(session, kind="virtual")
    assert {loc.code for loc in page.items} == {"A", "B", "C", "D"}


@pytest.mark.asyncio
async def test_get_not_found_raises(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    with pytest.raises(locations_service.InventoryLocationNotFoundError):
        await locations_service.get(session, uuid.uuid4())


@pytest.mark.asyncio
async def test_invalid_kind_raises(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    with pytest.raises(locations_service.InventoryLocationsServiceError):
        await locations_service.create(
            session,
            name="X",
            code="X",
            kind="not_a_kind",
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_invalid_cursor_raises(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    with pytest.raises(locations_service.InvalidCursorError):
        await locations_service.list_locations(session, cursor="not-a-cursor")
