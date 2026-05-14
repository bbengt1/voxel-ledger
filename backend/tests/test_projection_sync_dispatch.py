"""Sync-projection dispatch: ``EventStore.append`` invokes handlers in the
same transaction and a handler failure rolls back the event row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

# Import projections so handlers register. The side-effect import is what
# wires `test_event_projection` into the registry for these tests.
import app.projections  # noqa: F401
import pytest
import pytest_asyncio
from app.models import Base
from app.models.projection import ProjectionTestEvent
from app.projections import registry as projection_registry
from app.schemas.events import EventCreate
from app.services import event_store
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _make_event(value: str = "x") -> EventCreate:
    return EventCreate(
        type="test.TestEvent",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={"value": value},
        occurred_at=datetime.now(UTC),
        correlation_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_append_triggers_test_event_projection(session: AsyncSession, schema: None) -> None:
    ev = await event_store.append(_make_event("hello"), session=session)
    await session.commit()

    rows = (
        (
            await session.execute(
                select(ProjectionTestEvent).where(ProjectionTestEvent.event_id == ev.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].value == "hello"


@pytest.mark.asyncio
async def test_handler_failure_rolls_back_event_row(session: AsyncSession, schema: None) -> None:
    """A raising handler must keep the event log empty.

    Invariant: ``EventStore.append`` runs handlers inside the caller's
    transaction. If any handler raises, append re-raises. The caller is
    expected to roll back. The event row must not be persisted.
    """

    class BoomError(RuntimeError):
        pass

    @projection_registry.projection(
        event_type="test.TestEvent",
        name="boom_handler",
        read_model_tables=("projection_test_event",),
    )
    async def boom(event, session):
        raise BoomError("nope")

    try:
        with pytest.raises(BoomError):
            await event_store.append(_make_event("boom"), session=session)
        await session.rollback()

        # The event log should be empty: the failing handler aborted the txn.
        from app.models.event import Event

        count = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
        assert count == 0
    finally:
        # Clean up the dynamically-registered handler so it doesn't bleed
        # into other tests in the same session.
        projection_registry._BY_NAME.pop("boom_handler", None)
        for lst in projection_registry._BY_EVENT_TYPE.values():
            lst[:] = [h for h in lst if h.name != "boom_handler"]


@pytest.mark.asyncio
async def test_wildcard_handler_receives_every_event(session: AsyncSession, schema: None) -> None:
    received: list[str] = []

    @projection_registry.projection(
        event_type="*", name="wild", read_model_tables=("projection_test_event",)
    )
    async def wildcard(event, session):
        received.append(event.type)

    try:
        await event_store.append(_make_event("a"), session=session)
        await event_store.append(_make_event("b"), session=session)
        await session.commit()
        assert received == ["test.TestEvent", "test.TestEvent"]
    finally:
        projection_registry._BY_NAME.pop("wild", None)
        for lst in projection_registry._BY_EVENT_TYPE.values():
            lst[:] = [h for h in lst if h.name != "wild"]
