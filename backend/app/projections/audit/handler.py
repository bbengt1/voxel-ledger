"""Wildcard audit-log projection handler.

Subscribes to ``event_type='*'`` and writes one ``audit_log`` row per
event. The row is keyed on ``event_position`` (unique), so replay is
idempotent — re-projecting the same event would collide on the unique
constraint, and we short-circuit with a pre-check before INSERT.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.auth import User
from app.models.event import Event
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary
from app.projections.registry import projection

HANDLER_NAME = "audit_log_projection"
READ_MODEL_TABLES: tuple[str, ...] = ("audit_log",)


async def _resolve_actor(
    actor_user_id: uuid.UUID | None,
    session: AsyncSession,
) -> tuple[str | None, str | None]:
    """Look up the actor's email/role for denormalization.

    Returns ``(None, None)`` if no actor is recorded on the event. If the
    user has since been deleted, returns ``(None, None)`` as well — the
    foreign key in the audit_log column is ``ON DELETE SET NULL`` anyway.
    """
    if actor_user_id is None:
        return None, None
    result = await session.execute(select(User.email, User.role).where(User.id == actor_user_id))
    row = result.first()
    if row is None:
        return None, None
    email, role = row
    role_str = role.value if hasattr(role, "value") else (str(role) if role else None)
    return email, role_str


def _extract_ip(payload: dict[str, Any] | None) -> str | None:
    """Pull the IP address out of the event payload if the event type
    captured one. We use a stable key (``ip``) by convention so the
    projection doesn't have to know per-event-type field names."""
    if not payload:
        return None
    ip = payload.get("ip")
    if ip is None:
        return None
    return str(ip)


@projection(
    event_type="*",
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_audit(event: Event, session: AsyncSession) -> None:
    """Insert one audit_log row per event. Idempotent on ``event_position``."""
    # Idempotency: if we already wrote this event, skip. Cheap pre-check
    # so replays don't crash on the unique constraint. ``event_position``
    # is unique so a duplicate INSERT would otherwise raise.
    existing = await session.execute(
        select(AuditLog.id).where(AuditLog.event_position == event.position)
    )
    if existing.scalar_one_or_none() is not None:
        return

    actor_email, actor_role = await _resolve_actor(event.actor_user_id, session)
    actor_label = actor_email or "unknown"

    payload = event.payload or {}
    summary = render_summary(
        event.type,
        payload,
        actor_label=actor_label,
        aggregate_type=event.aggregate_type,
        aggregate_id=str(event.aggregate_id),
    )
    excerpt = compute_excerpt(event.type, payload)
    ip = _extract_ip(payload)

    session.add(
        AuditLog(
            event_id=event.id,
            event_position=event.position,
            event_type=event.type,
            actor_user_id=event.actor_user_id,
            actor_email=actor_email,
            actor_role=actor_role,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            occurred_at=event.occurred_at,
            summary=summary,
            ip_address=ip,
            payload_excerpt=excerpt,
        )
    )
    await session.flush()
