"""Auth audit emission.

Phase 1.4: ``log_auth_event`` now appends a real domain event via
``EventStore.append`` instead of emitting a structured log line. The
audit-log projection (wildcard subscriber) materializes each event into a
row in ``audit_log``, where the query API reads from.

Decision (documented in PR #?? body): we move *entirely* to events and
drop the legacy structured-log path. Reasons:

* The audit-log projection is the durable, queryable, hash-chained surface
  the spec asks for. Dual-emitting to stdout would just create a second
  source of truth we'd have to keep in sync.
* Operators who want grep-able stdout lines can derive them from the
  audit_log table; nothing about that workflow changes.
* The event log already gets shipped to backups via the same DB; logs
  alone never were.

Call sites pass the FastAPI ``session`` and ``Request`` (for IP capture)
through to this helper. We never persist tokens, password hashes, or
session identifiers in the event payload — see
``app/projections/audit/excerpts.py`` for the read-model whitelist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import auth as auth_events
from app.schemas.events import EventCreate
from app.services import event_store


async def emit_auth_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    ip: str | None,
) -> None:
    """Append one auth-bounded-context event.

    The caller owns the transaction; we don't commit. ``ip`` is folded
    into ``payload`` under a stable key so the audit projection can pull
    it out without per-event-type knowledge.
    """
    enriched = dict(payload)
    if ip:
        enriched["ip"] = ip

    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=auth_events.AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            payload=enriched,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers — one per concrete auth event. Each wrapper sets
# the right type string + aggregate_id and forwards the rest. Call sites
# in ``app/api/v1/auth.py`` use these; nobody outside that router should
# need to.
# ---------------------------------------------------------------------------


async def emit_login_succeeded(
    session: AsyncSession, *, user_id: uuid.UUID, email: str, ip: str | None
) -> None:
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_LOGIN_SUCCEEDED,
        aggregate_id=user_id,
        payload={"email": email, "user_id": str(user_id)},
        actor_user_id=user_id,
        ip=ip,
    )


async def emit_login_failed(
    session: AsyncSession,
    *,
    email: str,
    reason: str,
    ip: str | None,
) -> None:
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_LOGIN_FAILED,
        aggregate_id=auth_events.ANONYMOUS_AGGREGATE_ID,
        payload={"email": email, "reason": reason},
        actor_user_id=None,
        ip=ip,
    )


async def emit_login_inactive(session: AsyncSession, *, email: str, ip: str | None) -> None:
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_LOGIN_INACTIVE,
        aggregate_id=auth_events.ANONYMOUS_AGGREGATE_ID,
        payload={"email": email},
        actor_user_id=None,
        ip=ip,
    )


async def emit_refresh_rotated(
    session: AsyncSession, *, user_id: uuid.UUID, ip: str | None
) -> None:
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_REFRESH_ROTATED,
        aggregate_id=user_id,
        payload={"user_id": str(user_id)},
        actor_user_id=user_id,
        ip=ip,
    )


async def emit_family_revoked(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    reason: str,
    ip: str | None,
) -> None:
    payload: dict[str, Any] = {"reason": reason}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_FAMILY_REVOKED,
        aggregate_id=user_id or auth_events.ANONYMOUS_AGGREGATE_ID,
        payload=payload,
        actor_user_id=user_id,
        ip=ip,
    )


async def emit_logged_out(
    session: AsyncSession, *, user_id: uuid.UUID | None, ip: str | None
) -> None:
    payload: dict[str, Any] = {}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_LOGGED_OUT,
        aggregate_id=user_id or auth_events.ANONYMOUS_AGGREGATE_ID,
        payload=payload,
        actor_user_id=user_id,
        ip=ip,
    )


async def emit_rate_limited(session: AsyncSession, *, endpoint: str, ip: str | None) -> None:
    await emit_auth_event(
        session,
        event_type=auth_events.TYPE_RATE_LIMITED,
        aggregate_id=auth_events.ANONYMOUS_AGGREGATE_ID,
        payload={"endpoint": endpoint},
        actor_user_id=None,
        ip=ip,
    )
