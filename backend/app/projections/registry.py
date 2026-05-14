"""Projection handler registry.

A projection handler subscribes to one event type (or the wildcard ``"*"``)
and writes derived state to one or more read-model tables. Handlers run
synchronously inside the same DB transaction as ``EventStore.append``, so
a handler failure rolls back the event row itself.

Idempotency contract
--------------------
Handlers MUST be idempotent (replay-safe). The replay pipeline reads the
event log from ``position=0`` and dispatches every event through every
handler again; the resulting read model must equal what live appending
produced. In practice this means:

- INSERTs use the event's natural identity (``event_id``, ``aggregate_id``)
  as a primary key, or use ``ON CONFLICT DO NOTHING`` / merge semantics.
- Aggregations either replace a row keyed by aggregate_id, or accumulate
  in a way that is exactly reproducible from the same input sequence.

Cursor semantics
----------------
- During **live** projection (called from ``EventStore.append``) the
  ``projection_cursor`` row is NOT touched. Live appends own their cursor
  implicitly: ``last_position`` is always the event store's own
  ``max(position)``.
- During **replay** the cursor is advanced after each successfully handled
  event, inside the same transaction as the read-model write.

Wildcard handlers
-----------------
A handler may register with ``event_type="*"`` to receive every event
(used by the audit-log projection in #24). The unknown-event-type check
is skipped for wildcard handlers since by definition they accept anything.

TODO(phase-2): snapshot support for fast replay of large event streams.
TODO(phase-2): per-handler concurrency / out-of-band replay queue (currently
synchronous; see plan §4.2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import registry as event_registry
from app.models.event import Event

Handler = Callable[[Event, AsyncSession], Awaitable[None]]

WILDCARD: str = "*"


@dataclass(frozen=True)
class RegisteredHandler:
    """Bookkeeping for one registered handler."""

    name: str
    event_type: str
    fn: Handler
    read_model_tables: tuple[str, ...]


# event_type -> list of handlers (sorted by handler name on lookup).
_BY_EVENT_TYPE: dict[str, list[RegisteredHandler]] = {}
# handler_name -> RegisteredHandler.
_BY_NAME: dict[str, RegisteredHandler] = {}


class ProjectionRegistryError(Exception):
    """Base class for projection-registry errors."""


def projection(
    event_type: str,
    *,
    name: str,
    read_model_tables: tuple[str, ...],
) -> Callable[[Handler], Handler]:
    """Decorator: register a sync projection handler.

    ``event_type`` may be ``"*"`` for wildcard subscription. Otherwise it
    must already be in the event registry; an unknown event type fails
    loudly at import time, not at the first append.

    ``name`` is a stable identifier used by replay/rebuild scripts and the
    ``projection_cursor`` table. Two handlers cannot share a name.

    ``read_model_tables`` lists the tables this handler owns. Used by
    ``scripts/rebuild_projection.py`` to decide what to truncate.
    """
    if not name:
        raise ProjectionRegistryError("projection name must be non-empty")
    if not read_model_tables:
        raise ProjectionRegistryError(
            f"projection {name!r} must declare at least one read-model table "
            "(used by rebuild_projection.py)"
        )
    if event_type != WILDCARD and not event_registry.is_registered(event_type):
        raise ProjectionRegistryError(
            f"projection {name!r} subscribes to unregistered event type "
            f"{event_type!r}; register the event type before importing the "
            "projection module."
        )

    def decorator(fn: Handler) -> Handler:
        if name in _BY_NAME:
            existing = _BY_NAME[name]
            if existing.fn is fn and existing.event_type == event_type:
                # Idempotent re-registration (test module reload).
                return fn
            raise ProjectionRegistryError(f"projection name collision: {name!r} already registered")
        entry = RegisteredHandler(
            name=name,
            event_type=event_type,
            fn=fn,
            read_model_tables=tuple(read_model_tables),
        )
        _BY_EVENT_TYPE.setdefault(event_type, []).append(entry)
        _BY_NAME[name] = entry
        return fn

    return decorator


def handlers_for(event_type: str) -> list[RegisteredHandler]:
    """Return all handlers that should fire for ``event_type``.

    Includes wildcard subscribers. Sorted by handler name so dispatch
    order is deterministic regardless of import order.
    """
    specific = _BY_EVENT_TYPE.get(event_type, [])
    wildcard = _BY_EVENT_TYPE.get(WILDCARD, [])
    return sorted([*specific, *wildcard], key=lambda h: h.name)


def get_handler(name: str) -> RegisteredHandler:
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise ProjectionRegistryError(
            f"no projection registered under name {name!r}; known: " f"{sorted(_BY_NAME)}"
        ) from exc


def all_handlers() -> list[RegisteredHandler]:
    """Every registered handler, sorted by name (stable iteration order)."""
    return sorted(_BY_NAME.values(), key=lambda h: h.name)


def _reset_for_tests() -> None:
    """Test-only: clear the registry. Re-import projection modules to
    repopulate. Not exported."""
    _BY_EVENT_TYPE.clear()
    _BY_NAME.clear()
