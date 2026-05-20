"""Webhook fan-out projection (Phase 11.1, #193).

Wildcard subscriber: for every appended event, enqueue one
``webhook_delivery`` row per active ``webhook_subscription`` whose
``event_types`` list contains the event's type (or ``"*"``).

Runs inside the same transaction as the event append, so deliveries
are atomic with the originating event. The every-minute worker
drains pending deliveries in a separate transaction.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.projections.registry import projection
from app.services.webhooks import dispatcher

HANDLER_NAME = "webhook_fanout_projection"
READ_MODEL_TABLES = ("webhook_delivery",)


@projection(
    event_type="*",
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_webhook_fanout(event: Event, session: AsyncSession) -> None:
    await dispatcher.enqueue(event, session)
