"""Toy projection for ``test.TestEvent`` — TEST-ONLY.

Not a real business projection. Exists so the projection-engine plumbing
(registry, sync dispatch, replay parity) has something to exercise from
the unit test suite. Real projections will live alongside their bounded
context (sales, inventory, accounting, etc.) in later phases.

Read model: ``projection_test_event`` (event_id PK, value, recorded_at).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.projection import ProjectionTestEvent
from app.projections.registry import projection

HANDLER_NAME = "test_event_projection"
READ_MODEL_TABLES: tuple[str, ...] = ("projection_test_event",)


@projection(
    event_type="test.TestEvent",
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_test_event(event: Event, session: AsyncSession) -> None:
    """Insert one read-model row per ``test.TestEvent``.

    Idempotent: we key on ``event_id`` (the event's UUID), so replaying the
    same event is a no-op rather than a duplicate row. This is the contract
    every projection handler must honor — see ``app.projections.registry``.
    """
    # Cheap idempotency: if we already wrote this event, skip. Cheap and
    # dialect-neutral (Postgres + SQLite).
    existing = await session.execute(
        select(ProjectionTestEvent.event_id).where(ProjectionTestEvent.event_id == event.id)
    )
    if existing.scalar_one_or_none() is not None:
        return

    payload = event.payload or {}
    session.add(
        ProjectionTestEvent(
            event_id=event.id,
            value=str(payload.get("value", "")),
            recorded_at=event.recorded_at,
        )
    )
    await session.flush()
