"""Event-log append + read service.

The event log is the source of truth for the accounting domain. Every
mutation that affects financial state must append here inside the same
DB transaction as the side effect (inventory write, ledger write, ...).

Concurrency model
-----------------
Two writers cannot race on ``prev_event_hash``. We serialize appends with
``pg_advisory_xact_lock`` on a single well-known key — held for the rest
of the transaction, auto-released on commit/rollback. SQLite (used by
unit tests) is single-threaded and skips the lock entirely.

Hashing
-------
``canonical_bytes(row)`` is a JSON serialization with sorted keys,
no whitespace, ``ensure_ascii=False``, and ``default=str`` (so UUIDs and
``datetime`` objects serialize stably). It excludes ``event_hash`` (the
field we are computing) but INCLUDES ``prev_event_hash`` — that's how the
chain is bound together.

The previous-event lookup happens *inside* the transaction holding the
advisory lock, so by the time we read ``prev_event_hash`` no other writer
can have inserted ahead of us.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Eager-import projection modules so the @projection decorators run at
# startup. Without this, an event could be appended before any handler is
# registered. Side-effect import; the F401 is intentional.
import app.projections  # noqa: F401
from app.events import registry as event_registry
from app.models.event import Event
from app.projections import registry as projection_registry
from app.schemas.events import EventCreate

# Arbitrary but stable 64-bit key for the single-writer advisory lock.
# Chosen once; bake in stone. Documented here so future readers see the
# rationale instead of a magic number. The "E7E417" prefix is a wink at
# "event" — the rest is filler to fill the integer space.
EVENT_LOG_ADVISORY_LOCK_KEY: int = 0xE7E4170106

GENESIS_PREV_HASH: str = "0" * 64


class EventStoreError(Exception):
    """Base class for event-store errors."""


@dataclass
class _Canonical:
    """Helper so tests can introspect what was hashed without calling
    ``EventStore.append``. Not exported."""

    payload: dict[str, Any]
    bytes_: bytes
    digest: str


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        # Always include tz so the string round-trips deterministically.
        if value.tzinfo is None:
            raise TypeError("datetime values must be timezone-aware")
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def canonical_bytes(row: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding of an event row for hashing.

    - Keys are sorted.
    - No whitespace (``separators=(',', ':')``).
    - ``ensure_ascii=False`` so non-ASCII payloads hash the same bytes
      the DB will store.
    - ``event_hash`` is excluded (we are computing it).
    - ``prev_event_hash`` is INCLUDED — that's the chain link.
    - UUIDs and timezone-aware datetimes serialize via ``default``.
    """
    payload = {k: v for k, v in row.items() if k != "event_hash"}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def compute_event_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(row)).hexdigest()


def _ensure_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC.

    All event timestamps are persisted as ``TIMESTAMP WITH TIME ZONE`` in
    UTC. The Postgres driver returns aware datetimes; SQLite (tests)
    returns naive ones. The hash function needs to produce identical bytes
    regardless of which dialect wrote the row, so we normalize on read.
    """
    from datetime import UTC

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _row_for_hashing(event: Event) -> dict[str, Any]:
    """Build the dict we hash. Order doesn't matter (we sort keys), but
    field membership does — keep this in lockstep with the model."""
    return {
        "id": event.id,
        "position": event.position,
        "type": event.type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "payload": event.payload,
        "occurred_at": _ensure_utc(event.occurred_at),
        "recorded_at": _ensure_utc(event.recorded_at),
        "actor_user_id": event.actor_user_id,
        "correlation_id": event.correlation_id,
        "causation_id": event.causation_id,
        "prev_event_hash": event.prev_event_hash,
        "schema_version": event.schema_version,
    }


async def _acquire_advisory_lock(session: AsyncSession) -> None:
    """Hold the single-writer lock for the rest of the transaction.

    SQLite has no advisory locks; we skip the call (tests are single-
    threaded so there's nothing to serialize against).
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": EVENT_LOG_ADVISORY_LOCK_KEY},
    )


async def _allocate_position(session: AsyncSession) -> int:
    """Allocate the next ``position`` value.

    On Postgres we use the table's underlying bigserial sequence (named
    by PG as ``event_position_seq``) via ``nextval``. On SQLite we fall
    back to ``MAX(position) + 1`` — safe because SQLite tests don't run
    concurrent appends.
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        result = await session.execute(text("SELECT nextval('event_position_seq')"))
        return int(result.scalar_one())
    # SQLite branch (tests).
    result = await session.execute(text("SELECT COALESCE(MAX(position), 0) FROM event"))
    return int(result.scalar_one()) + 1


async def _fetch_prev_event_hash(session: AsyncSession) -> str:
    """Return the most recently appended event's ``event_hash``, or the
    genesis sentinel if the table is empty."""
    stmt = select(Event.event_hash).order_by(Event.position.desc()).limit(1)
    result = await session.execute(stmt)
    prev = result.scalar_one_or_none()
    return prev if prev is not None else GENESIS_PREV_HASH


async def append(event_data: EventCreate, *, session: AsyncSession) -> Event:
    """Append a single event to the log.

    The caller owns the transaction — we do not commit. The caller is
    responsible for committing (or rolling back) the surrounding unit of
    work, which is the only way the advisory lock and the inserted row
    both become durable atomically.
    """
    # 1. Validate the payload against the registered model. Unknown types
    # bubble up an UnknownEventTypeError; bad payloads an
    # InvalidEventPayloadError. Both are clear, programmer-readable errors.
    normalized_payload = event_registry.validate_payload(event_data.type, event_data.payload)

    # 2. Take the advisory lock. From here until commit/rollback we are
    # the only writer.
    await _acquire_advisory_lock(session)

    # 3. Determine prev_event_hash and allocate position. Both reads
    # happen under the lock so no race is possible.
    prev_hash = await _fetch_prev_event_hash(session)
    position = await _allocate_position(session)

    # 4. Build the row. recorded_at is filled by the DB default; we mirror
    # it in Python so the hash matches what's persisted. Use a tz-aware
    # UTC timestamp.
    from datetime import UTC

    recorded_at = datetime.now(UTC)
    event = Event(
        id=uuid.uuid4(),
        position=position,
        type=event_data.type,
        aggregate_type=event_data.aggregate_type,
        aggregate_id=event_data.aggregate_id,
        payload=normalized_payload,
        occurred_at=event_data.occurred_at,
        recorded_at=recorded_at,
        actor_user_id=event_data.actor_user_id,
        correlation_id=event_data.correlation_id,
        causation_id=event_data.causation_id,
        prev_event_hash=prev_hash,
        schema_version=event_data.schema_version,
        event_hash="",  # filled below
    )

    # 5. Compute the event hash and stamp it. The hash binds every field
    # including prev_event_hash, which is what makes the chain
    # tamper-evident.
    event.event_hash = compute_event_hash(_row_for_hashing(event))

    session.add(event)
    await session.flush()

    # 6. Synchronous projection dispatch.
    #
    # Every handler subscribed to this event type (plus wildcard handlers)
    # runs inside this same session/transaction. If any handler raises, we
    # re-raise without swallowing: the caller's transaction will roll back,
    # and the event row is never persisted from the caller's perspective.
    # This is the contract that keeps the event log and the read models in
    # strict consistency. See ``app/projections/registry.py``.
    #
    # The cursor table is NOT touched here — live appends own their cursor
    # implicitly (last_position == max(event.position)). The cursor is only
    # advanced during replay.
    for handler in projection_registry.handlers_for(event.type):
        await handler.fn(event, session)

    return event


async def read(
    session: AsyncSession,
    *,
    from_position: int = 0,
    to_position: int | None = None,
    batch_size: int = 1000,
) -> AsyncIterator[Event]:
    """Stream events in ``position`` order.

    Async generator — yields one event at a time but fetches in batches so
    we never load everything into memory at once. The caller controls
    transaction lifetime.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    cursor = max(0, from_position)
    while True:
        stmt = (
            select(Event)
            .where(Event.position > cursor)
            .order_by(Event.position.asc())
            .limit(batch_size)
        )
        if to_position is not None:
            stmt = stmt.where(Event.position <= to_position)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        if not rows:
            return
        for row in rows:
            yield row
            cursor = row.position
        if len(rows) < batch_size:
            return


@dataclass
class VerifyResult:
    ok: bool
    last_position: int | None
    broken_at_position: int | None
    events_checked: int


async def verify_chain(
    session: AsyncSession,
    *,
    from_position: int = 0,
    to_position: int | None = None,
    batch_size: int = 1000,
) -> VerifyResult:
    """Walk the chain, recompute every hash, and check linkage.

    Two checks per event:
      1. ``prev_event_hash`` must equal the previously yielded event's
         ``event_hash`` (or the genesis sentinel for position 1, only
         when ``from_position`` covers it).
      2. ``compute_event_hash(row)`` must equal the stored ``event_hash``.

    Note: when ``from_position > 0`` and the first verified event is not
    position 1, we accept the row's stored ``prev_event_hash`` as the
    starting link (we trust the slice boundary). Inside the window the
    chain is verified strictly.
    """
    expected_prev: str | None = None
    last_position: int | None = None
    events_checked = 0

    async for ev in read(
        session,
        from_position=from_position,
        to_position=to_position,
        batch_size=batch_size,
    ):
        if expected_prev is None:
            # First event in the window. If from_position == 0 and this
            # is position 1, the prev_event_hash must be the genesis
            # sentinel; otherwise accept whatever's stored and use it as
            # the seed for the rest of the walk.
            if from_position == 0 and ev.position == 1 and ev.prev_event_hash != GENESIS_PREV_HASH:
                return VerifyResult(
                    ok=False,
                    last_position=last_position,
                    broken_at_position=ev.position,
                    events_checked=events_checked,
                )
        else:
            if ev.prev_event_hash != expected_prev:
                return VerifyResult(
                    ok=False,
                    last_position=last_position,
                    broken_at_position=ev.position,
                    events_checked=events_checked,
                )

        recomputed = compute_event_hash(_row_for_hashing(ev))
        if recomputed != ev.event_hash:
            return VerifyResult(
                ok=False,
                last_position=last_position,
                broken_at_position=ev.position,
                events_checked=events_checked,
            )

        expected_prev = ev.event_hash
        last_position = ev.position
        events_checked += 1

    return VerifyResult(
        ok=True,
        last_position=last_position,
        broken_at_position=None,
        events_checked=events_checked,
    )
