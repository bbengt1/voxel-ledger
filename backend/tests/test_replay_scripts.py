"""Exercise the replay/rebuild CLI scripts.

We call the script's ``_run`` coroutine directly from async tests (calling
``main()`` would nest ``asyncio.run`` inside the test loop). The script's
DB plumbing is monkey-patched to a test-controlled engine to avoid
touching real settings.
"""

from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime

import app.projections  # noqa: F401
import pytest
import pytest_asyncio
from app.models import Base
from app.models.projection import ProjectionCursor, ProjectionTestEvent
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


def _patch_script_deps(monkeypatch, script_module, engine, factory) -> None:
    """Wire the script to the test engine without touching real settings."""

    async def _noop_dispose(self):
        return None

    monkeypatch.setattr(script_module, "load_settings", lambda: object())
    monkeypatch.setattr(script_module, "make_engine", lambda _s: engine)
    monkeypatch.setattr(script_module, "make_session_factory", lambda _e: factory)
    # Avoid real dispose so the engine survives for assertions.
    monkeypatch.setattr(engine.__class__, "dispose", _noop_dispose)


@pytest.mark.asyncio
async def test_replay_script_main_runs(engine, schema, monkeypatch) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        for i in range(3):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    from app.projections.replay import delete_cursor, truncate_read_model_tables

    async with factory() as s:
        await truncate_read_model_tables(s, ("projection_test_event",))
        await delete_cursor(s, "test_event_projection")
        await s.commit()

    from scripts import replay_projections

    _patch_script_deps(monkeypatch, replay_projections, engine, factory)

    args = argparse.Namespace(handler="test_event_projection", from_position=0, dry_run=False)
    rc = await replay_projections._run(args)
    assert rc == 0

    async with factory() as s:
        rows = (await s.execute(select(ProjectionTestEvent))).scalars().all()
        cursor = (
            await s.execute(
                select(ProjectionCursor.last_position).where(
                    ProjectionCursor.handler_name == "test_event_projection"
                )
            )
        ).scalar_one()
    assert len(rows) == 3
    assert cursor == 3


@pytest.mark.asyncio
async def test_replay_script_dry_run_writes_nothing(engine, schema, monkeypatch) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        for i in range(2):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    from app.projections.replay import delete_cursor, truncate_read_model_tables

    async with factory() as s:
        await truncate_read_model_tables(s, ("projection_test_event",))
        await delete_cursor(s, "test_event_projection")
        await s.commit()

    from scripts import replay_projections

    _patch_script_deps(monkeypatch, replay_projections, engine, factory)

    args = argparse.Namespace(handler="test_event_projection", from_position=0, dry_run=True)
    rc = await replay_projections._run(args)
    assert rc == 0

    async with factory() as s:
        rows = (await s.execute(select(ProjectionTestEvent))).scalars().all()
        cursor = (
            await s.execute(
                select(ProjectionCursor.last_position).where(
                    ProjectionCursor.handler_name == "test_event_projection"
                )
            )
        ).scalar_one_or_none()
    assert rows == []
    assert cursor is None


@pytest.mark.asyncio
async def test_replay_script_all_runs_every_handler(engine, schema, monkeypatch) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        for i in range(2):
            await event_store.append(_make_event(f"v{i}"), session=s)
        await s.commit()

    from app.projections.replay import delete_cursor, truncate_read_model_tables

    async with factory() as s:
        await truncate_read_model_tables(s, ("projection_test_event",))
        await delete_cursor(s, "test_event_projection")
        await s.commit()

    from scripts import replay_projections

    _patch_script_deps(monkeypatch, replay_projections, engine, factory)

    args = argparse.Namespace(handler="all", from_position=0, dry_run=False)
    rc = await replay_projections._run(args)
    assert rc == 0

    async with factory() as s:
        rows = (await s.execute(select(ProjectionTestEvent))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_replay_script_unknown_handler_raises(monkeypatch) -> None:
    from scripts import replay_projections

    class _Eng:
        async def dispose(self):
            return None

    monkeypatch.setattr(replay_projections, "load_settings", lambda: object())
    monkeypatch.setattr(replay_projections, "make_engine", lambda _s: _Eng())
    monkeypatch.setattr(replay_projections, "make_session_factory", lambda _e: object())

    from app.projections.registry import ProjectionRegistryError

    args = argparse.Namespace(handler="nope", from_position=None, dry_run=False)
    with pytest.raises(ProjectionRegistryError):
        await replay_projections._run(args)


def test_rebuild_script_arg_parsing() -> None:
    """``--yes-really`` is a flag, not a value."""
    from scripts import rebuild_projection

    args = rebuild_projection._parse_args(["--handler", "test_event_projection", "--yes-really"])
    assert args.handler == "test_event_projection"
    assert args.yes_really is True

    args = rebuild_projection._parse_args(["--handler", "x"])
    assert args.yes_really is False
