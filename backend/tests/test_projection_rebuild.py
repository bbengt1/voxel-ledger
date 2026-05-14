"""rebuild_projection script behavior: truncate + replay only with
``--yes-really``; safe no-op otherwise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.projections  # noqa: F401
import pytest
import pytest_asyncio
from app.models import Base
from app.models.projection import ProjectionCursor, ProjectionTestEvent
from app.projections import registry as projection_registry
from app.projections.replay import truncate_read_model_tables
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


@pytest.mark.asyncio
async def test_truncate_clears_only_declared_tables(engine, schema) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    handler = projection_registry.get_handler("test_event_projection")

    async with factory() as s:
        for i in range(3):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    async with factory() as s:
        count = (await s.execute(select(ProjectionTestEvent))).scalars().all()
    assert len(count) == 3

    async with factory() as s:
        await truncate_read_model_tables(s, handler.read_model_tables)
        await s.commit()

    async with factory() as s:
        # Read model gone.
        rows = (await s.execute(select(ProjectionTestEvent))).scalars().all()
        assert rows == []
        # Event log untouched.
        from app.models.event import Event

        events = (await s.execute(select(Event))).scalars().all()
        assert len(events) == 3


def test_rebuild_dry_preview_is_noop(monkeypatch) -> None:
    """Without ``--yes-really`` the rebuild script must not touch the DB.

    We monkey-patch the script's engine factory to a sentinel so that any
    attempt to actually do work would blow up loudly.
    """
    from scripts import rebuild_projection

    truncation_calls: list = []
    replay_calls: list = []

    class _FakeEngine:
        async def dispose(self):
            return None

    def _fake_engine(_settings):
        return _FakeEngine()

    def _fake_factory(_engine):
        return object()

    async def _no_truncate(*args, **kwargs):
        truncation_calls.append(args)

    async def _no_replay(*args, **kwargs):
        replay_calls.append(args)

    monkeypatch.setattr(rebuild_projection, "load_settings", lambda: object())
    monkeypatch.setattr(rebuild_projection, "make_engine", _fake_engine)
    monkeypatch.setattr(rebuild_projection, "make_session_factory", _fake_factory)
    monkeypatch.setattr(rebuild_projection, "truncate_read_model_tables", _no_truncate)
    monkeypatch.setattr(rebuild_projection, "replay_handler", _no_replay)

    rc = rebuild_projection.main(["--handler", "test_event_projection"])
    assert rc == 0
    assert truncation_calls == []
    assert replay_calls == []


@pytest.mark.asyncio
async def test_rebuild_yes_really_truncates_and_replays(engine, schema) -> None:
    """End-to-end behavior of the destructive branch (without going through
    the script's settings/engine bootstrap)."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    handler = projection_registry.get_handler("test_event_projection")

    async with factory() as s:
        for i in range(3):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    # Simulate the script's destructive branch.
    from app.projections.replay import (
        delete_cursor,
    )
    from app.projections.replay import (
        replay_handler as _replay,
    )
    from app.projections.replay import (
        truncate_read_model_tables as _truncate,
    )

    async with factory() as s:
        await _truncate(s, handler.read_model_tables)
        await delete_cursor(s, handler.name)
        await s.commit()

    result = await _replay(handler, factory, from_position=0)
    assert result.events_processed == 3
    async with factory() as s:
        rows = (await s.execute(select(ProjectionTestEvent))).scalars().all()
    assert len(rows) == 3
    async with factory() as s:
        cursor = (
            await s.execute(
                select(ProjectionCursor.last_position).where(
                    ProjectionCursor.handler_name == handler.name
                )
            )
        ).scalar_one()
    assert cursor == 3
