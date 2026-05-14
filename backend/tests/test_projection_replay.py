"""Replay-parity test: live appending and replay-from-zero produce the
same read-model state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.projections  # noqa: F401  (register handlers)
import pytest
import pytest_asyncio
from app.models import Base
from app.models.projection import ProjectionCursor, ProjectionTestEvent
from app.projections import registry as projection_registry
from app.projections.replay import (
    delete_cursor,
    replay_handler,
    truncate_read_model_tables,
)
from app.schemas.events import EventCreate
from app.services import event_store
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _make_event(value: str) -> EventCreate:
    return EventCreate(
        type="test.TestEvent",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={"value": value},
        occurred_at=datetime.now(UTC),
        correlation_id=uuid.uuid4(),
    )


async def _snapshot(session) -> list[tuple[str, str]]:
    rows = (
        (await session.execute(select(ProjectionTestEvent).order_by(ProjectionTestEvent.value)))
        .scalars()
        .all()
    )
    return [(str(r.event_id), r.value) for r in rows]


@pytest.mark.asyncio
async def test_replay_from_zero_matches_live_projection(engine, schema) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    handler = projection_registry.get_handler("test_event_projection")

    # 1. Write N events live (sync projection writes the read model).
    async with factory() as s:
        for i in range(7):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    async with factory() as s:
        live_snapshot = await _snapshot(s)
    assert len(live_snapshot) == 7

    # 2. Wipe the read model and the cursor.
    async with factory() as s:
        await truncate_read_model_tables(s, handler.read_model_tables)
        await delete_cursor(s, handler.name)
        await s.commit()

    async with factory() as s:
        assert await _snapshot(s) == []

    # 3. Replay from position 0.
    result = await replay_handler(handler, factory, from_position=0)
    assert result.events_processed == 7
    assert result.last_position == 7
    assert not result.dry_run

    # 4. Parity check.
    async with factory() as s:
        replayed_snapshot = await _snapshot(s)
    assert replayed_snapshot == live_snapshot

    # 5. Cursor advanced atomically.
    async with factory() as s:
        cursor = (
            await s.execute(
                select(ProjectionCursor.last_position).where(
                    ProjectionCursor.handler_name == handler.name
                )
            )
        ).scalar_one()
    assert cursor == 7


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(engine, schema) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    handler = projection_registry.get_handler("test_event_projection")

    async with factory() as s:
        for i in range(3):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    async with factory() as s:
        await truncate_read_model_tables(s, handler.read_model_tables)
        await delete_cursor(s, handler.name)
        await s.commit()

    result = await replay_handler(handler, factory, from_position=0, dry_run=True)
    assert result.events_processed == 3
    assert result.dry_run

    async with factory() as s:
        assert await _snapshot(s) == []
        cursor = (
            await s.execute(
                select(ProjectionCursor.last_position).where(
                    ProjectionCursor.handler_name == handler.name
                )
            )
        ).scalar_one_or_none()
    assert cursor is None


@pytest.mark.asyncio
async def test_replay_resumes_from_stored_cursor(engine, schema) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    handler = projection_registry.get_handler("test_event_projection")

    async with factory() as s:
        for i in range(4):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    # Truncate the read model but leave a fabricated cursor at position 2.
    async with factory() as s:
        await truncate_read_model_tables(s, handler.read_model_tables)
        await delete_cursor(s, handler.name)
        s.add(ProjectionCursor(handler_name=handler.name, last_position=2))
        await s.commit()

    # Default replay (no --from-position) should resume from 2 and only
    # process events 3 and 4.
    result = await replay_handler(handler, factory)
    assert result.events_processed == 2
    assert result.last_position == 4

    async with factory() as s:
        snapshot = await _snapshot(s)
    assert len(snapshot) == 2
