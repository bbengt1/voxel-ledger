"""EventStore integration tests against real Postgres.

These tests cover behavior that SQLite cannot model:
  - Advisory-lock-mediated single-writer guarantee under concurrency.
  - The ``BEFORE UPDATE OR DELETE`` immutability trigger.
  - Position monotonicity under concurrent independent sessions.

Skip cleanly when Docker is unavailable via the ``postgres_url`` fixture.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.schemas.events import EventCreate
from app.services import event_store
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


def _evt(value: str = "x") -> EventCreate:
    return EventCreate(
        type="test.TestEvent",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={"value": value},
        occurred_at=datetime.now(UTC),
        correlation_id=uuid.uuid4(),
    )


@pytest_asyncio.fixture
async def pg_engine(postgres_url: str):
    eng = create_async_engine(postgres_url, future=True)
    # Build the schema via metadata, then layer in the PG-only DDL the
    # 0003 migration adds (sequence + immutability trigger). We mirror
    # the migration rather than running alembic here to keep the
    # integration test self-contained and quick.
    from app.models import Base

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Mirror what the alembic migration sets up for PG.
        await conn.execute(
            text("CREATE SEQUENCE IF NOT EXISTS event_position_seq " "OWNED BY event.position")
        )
        await conn.execute(
            text(
                "ALTER TABLE event ALTER COLUMN position "
                "SET DEFAULT nextval('event_position_seq')"
            )
        )
        await conn.execute(
            text(
                "SELECT setval('event_position_seq', "
                "COALESCE((SELECT MAX(position) FROM event), 0) + 1, false)"
            )
        )
        await conn.execute(
            text(
                "CREATE OR REPLACE FUNCTION event_log_block_mutation() "
                "RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'event log is append-only (op=%, position=%)', "
                "TG_OP, COALESCE(OLD.position, NEW.position); "
                "END; $$ LANGUAGE plpgsql"
            )
        )
        await conn.execute(
            text(
                "CREATE TRIGGER event_log_block_mutation_trg "
                "BEFORE UPDATE OR DELETE ON event "
                "FOR EACH ROW EXECUTE FUNCTION event_log_block_mutation()"
            )
        )

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_pg_append_basic(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        ev = await event_store.append(_evt("a"), session=s)
        await s.commit()
    assert ev.position == 1
    assert ev.prev_event_hash == event_store.GENESIS_PREV_HASH


@pytest.mark.asyncio
async def test_pg_immutability_blocks_update(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        ev = await event_store.append(_evt("a"), session=s)
        await s.commit()
        with pytest.raises(Exception) as exc:
            await s.execute(
                text('UPDATE event SET payload = \'{"value":"hack"}\' WHERE id = :i'),
                {"i": ev.id},
            )
            await s.commit()
        assert "append-only" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_pg_immutability_blocks_delete(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        ev = await event_store.append(_evt("a"), session=s)
        await s.commit()
        with pytest.raises(Exception) as exc:
            await s.execute(text("DELETE FROM event WHERE id = :i"), {"i": ev.id})
            await s.commit()
        assert "append-only" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_pg_concurrent_appends_keep_chain_intact(pg_session_factory) -> None:
    """Spawn N concurrent appends across independent sessions and verify
    the final chain is intact and positions are contiguous 1..N."""
    n = 20

    async def one_append(i: int) -> None:
        async with pg_session_factory() as s:
            await event_store.append(_evt(f"v{i}"), session=s)
            await s.commit()

    await asyncio.gather(*(one_append(i) for i in range(n)))

    async with pg_session_factory() as s:
        positions = []
        async for ev in event_store.read(s):
            positions.append(ev.position)
        assert positions == list(range(1, n + 1))

        result = await event_store.verify_chain(s)
        assert result.ok, result
        assert result.events_checked == n
        assert result.last_position == n


@pytest.mark.asyncio
async def test_pg_verify_chain_detects_corruption(pg_session_factory) -> None:
    """Use a temporary trigger drop to corrupt a row, then re-enable.

    This is the only test where we deliberately bypass immutability.
    """
    async with pg_session_factory() as s:
        for i in range(3):
            await event_store.append(_evt(f"v{i}"), session=s)
        await s.commit()

        await s.execute(text("ALTER TABLE event DISABLE TRIGGER event_log_block_mutation_trg"))
        await s.execute(
            text("UPDATE event SET event_hash = :h WHERE position = 2"),
            {"h": "f" * 64},
        )
        await s.execute(text("ALTER TABLE event ENABLE TRIGGER event_log_block_mutation_trg"))
        await s.commit()

        result = await event_store.verify_chain(s)
        assert result.ok is False
        assert result.broken_at_position == 2


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_pg_benchmark_1000_appends(pg_session_factory) -> None:
    """Smoke benchmark — 1,000 sequential appends should finish in <5s on
    a local PG instance. Marked benchmark so it skips by default."""
    import time

    start = time.monotonic()
    async with pg_session_factory() as s:
        for i in range(1000):
            await event_store.append(_evt(f"v{i}"), session=s)
        await s.commit()
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"1000 appends took {elapsed:.2f}s"
