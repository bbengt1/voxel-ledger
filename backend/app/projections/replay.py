"""Replay engine for projection handlers.

Replay reads events from the event log in position order and dispatches
each one to a handler. The handler's read-model write and the cursor
advance happen in the same transaction, so a crash mid-replay leaves the
cursor pointing exactly at the last successfully projected event.

Live projection (from ``EventStore.append``) does not use this module —
it dispatches inline. Replay is for backfills, rebuilds, and the nightly
parity check.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.projection import ProjectionCursor
from app.projections.registry import RegisteredHandler
from app.services import event_store

log = logging.getLogger(__name__)

PROGRESS_INTERVAL: int = 1000


@dataclass
class ReplayResult:
    handler_name: str
    events_processed: int
    last_position: int
    dry_run: bool


async def _get_cursor_position(session: AsyncSession, handler_name: str) -> int:
    result = await session.execute(
        select(ProjectionCursor.last_position).where(ProjectionCursor.handler_name == handler_name)
    )
    row = result.scalar_one_or_none()
    return int(row) if row is not None else 0


async def _upsert_cursor(session: AsyncSession, handler_name: str, position: int) -> None:
    """Advance the cursor row for ``handler_name`` to ``position``.

    Dialect-neutral: try UPDATE, fall back to INSERT. Both go through the
    same transaction as the read-model write.
    """
    res = await session.execute(
        update(ProjectionCursor)
        .where(ProjectionCursor.handler_name == handler_name)
        .values(last_position=position)
    )
    if res.rowcount == 0:
        await session.execute(
            insert(ProjectionCursor).values(handler_name=handler_name, last_position=position)
        )


async def delete_cursor(session: AsyncSession, handler_name: str) -> None:
    """Remove a handler's cursor row. Used by rebuild."""
    await session.execute(
        delete(ProjectionCursor).where(ProjectionCursor.handler_name == handler_name)
    )


async def replay_handler(
    handler: RegisteredHandler,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    from_position: int | None = None,
    dry_run: bool = False,
) -> ReplayResult:
    """Replay every event from ``from_position`` through ``handler``.

    One transaction per event so the cursor advances atomically with the
    read-model write. ``from_position=None`` resumes from the stored
    cursor; pass ``0`` to replay from the beginning.

    Dry-run mode rolls back each transaction so nothing is written. We
    still log the work that would have been done.
    """
    if from_position is None:
        async with session_factory() as cursor_session:
            from_position = await _get_cursor_position(cursor_session, handler.name)

    processed = 0
    last_position = from_position

    # Stream events through a read-only session, dispatch each in its own
    # write session. This keeps transactions small and lets the cursor
    # advance one row at a time.
    async with session_factory() as read_session:
        async for ev in event_store.read(read_session, from_position=from_position):
            if handler.event_type != "*" and ev.type != handler.event_type:
                # The handler doesn't subscribe to this type — skip without
                # advancing its cursor. (Wildcard handlers see everything.)
                continue

            async with session_factory() as write_session:
                await handler.fn(ev, write_session)
                await _upsert_cursor(write_session, handler.name, ev.position)
                if dry_run:
                    await write_session.rollback()
                else:
                    await write_session.commit()

            processed += 1
            last_position = ev.position
            if processed % PROGRESS_INTERVAL == 0:
                log.info(
                    "replay.progress handler=%s processed=%d last_position=%d",
                    handler.name,
                    processed,
                    last_position,
                )

    log.info(
        "replay.done handler=%s processed=%d last_position=%d dry_run=%s",
        handler.name,
        processed,
        last_position,
        dry_run,
    )
    return ReplayResult(
        handler_name=handler.name,
        events_processed=processed,
        last_position=last_position,
        dry_run=dry_run,
    )


async def truncate_read_model_tables(session: AsyncSession, tables: tuple[str, ...]) -> None:
    """Empty the projection's declared read-model tables.

    Postgres uses ``TRUNCATE`` (fast, resets sequences). SQLite (tests)
    has no TRUNCATE so we fall back to ``DELETE``.
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""
    for table in tables:
        if dialect == "postgresql":
            # CASCADE handles potential FKs from later-phase tables.
            await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
        else:
            await session.execute(text(f'DELETE FROM "{table}"'))
