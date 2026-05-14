"""EventStore append + read happy-path tests against SQLite-fast."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.models import Base
from app.schemas.events import EventCreate
from app.services import event_store
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
async def test_append_returns_populated_row(session: AsyncSession, schema: None) -> None:
    ev = await event_store.append(_make_event("a"), session=session)
    assert ev.position == 1
    assert ev.prev_event_hash == event_store.GENESIS_PREV_HASH
    assert len(ev.event_hash) == 64
    assert ev.recorded_at is not None
    await session.commit()


@pytest.mark.asyncio
async def test_chain_links_across_three_appends(session: AsyncSession, schema: None) -> None:
    e1 = await event_store.append(_make_event("a"), session=session)
    e2 = await event_store.append(_make_event("b"), session=session)
    e3 = await event_store.append(_make_event("c"), session=session)
    assert e2.prev_event_hash == e1.event_hash
    assert e3.prev_event_hash == e2.event_hash
    assert [e1.position, e2.position, e3.position] == [1, 2, 3]
    await session.commit()


@pytest.mark.asyncio
async def test_unknown_event_type_rejected(session: AsyncSession, schema: None) -> None:
    bad = EventCreate(
        type="nope.NotARealType",
        aggregate_type="t",
        aggregate_id=uuid.uuid4(),
        payload={"value": "x"},
        occurred_at=datetime.now(UTC),
        correlation_id=uuid.uuid4(),
    )
    with pytest.raises(Exception) as exc:
        await event_store.append(bad, session=session)
    # Surfaces the registry's UnknownEventTypeError.
    assert "not registered" in str(exc.value)


@pytest.mark.asyncio
async def test_invalid_payload_rejected(session: AsyncSession, schema: None) -> None:
    bad = EventCreate(
        type="test.TestEvent",
        aggregate_type="t",
        aggregate_id=uuid.uuid4(),
        payload={"wrong_field": 1},
        occurred_at=datetime.now(UTC),
        correlation_id=uuid.uuid4(),
    )
    with pytest.raises(Exception) as exc:
        await event_store.append(bad, session=session)
    assert "failed validation" in str(exc.value)


@pytest.mark.asyncio
async def test_read_yields_in_position_order(session: AsyncSession, schema: None) -> None:
    appended = []
    for i in range(5):
        appended.append(await event_store.append(_make_event(f"v{i}"), session=session))
    await session.commit()

    seen = []
    async for ev in event_store.read(session, batch_size=2):
        seen.append(ev.position)
    assert seen == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_read_respects_from_and_to_position(session: AsyncSession, schema: None) -> None:
    for i in range(10):
        await event_store.append(_make_event(f"v{i}"), session=session)
    await session.commit()

    positions = [
        ev.position async for ev in event_store.read(session, from_position=3, to_position=7)
    ]
    assert positions == [4, 5, 6, 7]


@pytest.mark.asyncio
async def test_read_rejects_bad_batch_size(session: AsyncSession, schema: None) -> None:
    with pytest.raises(ValueError):
        async for _ in event_store.read(session, batch_size=0):
            pass


@pytest.mark.asyncio
async def test_verify_chain_ok(session: AsyncSession, schema: None) -> None:
    for i in range(4):
        await event_store.append(_make_event(f"v{i}"), session=session)
    await session.commit()

    result = await event_store.verify_chain(session)
    assert result.ok is True
    assert result.last_position == 4
    assert result.broken_at_position is None
    assert result.events_checked == 4


@pytest.mark.asyncio
async def test_verify_chain_empty_log(session: AsyncSession, schema: None) -> None:
    result = await event_store.verify_chain(session)
    assert result.ok is True
    assert result.last_position is None
    assert result.events_checked == 0


@pytest.mark.asyncio
async def test_verify_chain_detects_hash_corruption(session: AsyncSession, schema: None) -> None:
    """Tamper with a row's event_hash via direct SQL and confirm the
    verifier flags the position where the chain breaks."""
    from sqlalchemy import text

    for i in range(3):
        await event_store.append(_make_event(f"v{i}"), session=session)
    await session.commit()

    # Replace position-2's event_hash with garbage.
    await session.execute(
        text("UPDATE event SET event_hash = :h WHERE position = 2"),
        {"h": "f" * 64},
    )
    await session.commit()

    result = await event_store.verify_chain(session)
    assert result.ok is False
    # The verifier walks 1 -> ok, then 2 -> stored hash != recomputed hash.
    assert result.broken_at_position == 2
    assert result.last_position == 1
