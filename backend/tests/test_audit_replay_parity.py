"""Replay parity: truncate audit_log, rebuild, assert same rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models import Base
from app.models.audit import AuditLog
from app.projections import registry as projection_registry
from app.projections.audit.handler import HANDLER_NAME
from app.projections.replay import replay_handler, truncate_read_model_tables
from app.schemas.events import EventCreate
from app.services import event_store
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_replay_parity(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Write N varied events.
    async with factory() as s:
        for i in range(5):
            await event_store.append(
                EventCreate(
                    type="test.TestEvent",
                    aggregate_type="test",
                    aggregate_id=uuid.uuid4(),
                    payload={"value": f"v{i}"},
                    occurred_at=datetime.now(UTC),
                    correlation_id=uuid.uuid4(),
                ),
                session=s,
            )
        await s.commit()

    # Snapshot audit_log.
    async with factory() as s:
        before = [
            (r.event_position, r.event_type, r.summary)
            for r in (await s.execute(select(AuditLog).order_by(AuditLog.event_position))).scalars()
        ]
    assert len(before) == 5

    # Truncate, also delete projection cursors so replay starts from 0.
    async with factory() as s:
        await truncate_read_model_tables(s, ("audit_log",))
        from app.models.projection import ProjectionCursor

        await s.execute(delete(ProjectionCursor))
        await s.commit()

    # Replay.
    handler = projection_registry.get_handler(HANDLER_NAME)
    await replay_handler(handler, factory, from_position=0)

    async with factory() as s:
        after = [
            (r.event_position, r.event_type, r.summary)
            for r in (await s.execute(select(AuditLog).order_by(AuditLog.event_position))).scalars()
        ]
    assert after == before
