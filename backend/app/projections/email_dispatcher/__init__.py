"""Email dispatcher projection (Phase 7.7, #115).

Consumes ``ar.QuoteSent``, ``ar.InvoiceIssued``, and (when Phase 7.5
lands) ``ar.RecurringInvoiceMaterialized``. For each, renders the
appropriate email via the renderers in
:mod:`app.services.email.renderers` and calls
:func:`app.services.email.enqueue_email`.

The dispatcher is replay-safe because ``enqueue_email`` honors the
``(kind, subject_kind, subject_id)`` unique partial index — re-emitting
the same upstream event is a no-op.

Defensive recurring import
--------------------------
Phase 7.5 (recurring invoices) is in flight; the ``RecurringInvoiceMaterialized``
event type may not yet exist at import time on a branch that doesn't
include it. We wrap the recurring registration in a try/except so a
missing dependency degrades to "no recurring email" rather than a
crash at boot.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ar as ar_events
from app.models.email_message import EmailKind
from app.models.event import Event
from app.projections.registry import projection
from app.services.email import enqueue_email
from app.services.email.renderers import invoice as invoice_renderer
from app.services.email.renderers import quote as quote_renderer

log = logging.getLogger(__name__)

READ_MODEL_TABLES: tuple[str, ...] = ("email_message",)


async def _to_customer_email(customer_id: uuid.UUID, session: AsyncSession) -> str | None:
    from sqlalchemy import select

    from app.models.customer import Customer

    row = (
        await session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.primary_email


@projection(
    event_type=ar_events.TYPE_QUOTE_SENT,
    name="email_dispatcher_quote_sent",
    read_model_tables=READ_MODEL_TABLES,
)
async def on_quote_sent(event: Event, session: AsyncSession) -> None:
    payload = event.payload or {}
    quote_id_raw = payload.get("quote_id")
    customer_id_raw = payload.get("customer_id")
    if not quote_id_raw or not customer_id_raw:
        return
    quote_id = uuid.UUID(str(quote_id_raw))
    customer_id = uuid.UUID(str(customer_id_raw))

    to_address = await _to_customer_email(customer_id, session)
    if not to_address:
        log.info("email_dispatcher.skip_no_email", extra={"quote_id": str(quote_id)})
        return

    rendered = await quote_renderer.render(quote_id, session=session)
    await enqueue_email(
        EmailKind.QUOTE,
        subject_kind="quote",
        subject_id=quote_id,
        to_address=to_address,
        subject=rendered.subject,
        body_html=rendered.body_html,
        body_text=rendered.body_text,
        attachments=rendered.attachments,
        session=session,
    )


@projection(
    event_type=ar_events.TYPE_INVOICE_ISSUED,
    name="email_dispatcher_invoice_issued",
    read_model_tables=READ_MODEL_TABLES,
)
async def on_invoice_issued(event: Event, session: AsyncSession) -> None:
    payload = event.payload or {}
    invoice_id_raw = payload.get("invoice_id")
    customer_id_raw = payload.get("customer_id")
    if not invoice_id_raw or not customer_id_raw:
        return
    invoice_id = uuid.UUID(str(invoice_id_raw))
    customer_id = uuid.UUID(str(customer_id_raw))

    to_address = await _to_customer_email(customer_id, session)
    if not to_address:
        log.info("email_dispatcher.skip_no_email", extra={"invoice_id": str(invoice_id)})
        return

    rendered = await invoice_renderer.render(invoice_id, session=session)
    await enqueue_email(
        EmailKind.INVOICE,
        subject_kind="invoice",
        subject_id=invoice_id,
        to_address=to_address,
        subject=rendered.subject,
        body_html=rendered.body_html,
        body_text=rendered.body_text,
        attachments=rendered.attachments,
        session=session,
    )


# --- Recurring invoices: defensive registration ---
# Phase 7.5 may or may not be merged when this lands. If the event type
# isn't registered, skip the handler.
try:
    RECURRING_EVENT_TYPE = ar_events.TYPE_RECURRING_INVOICE_MATERIALIZED  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover — depends on merge order
    RECURRING_EVENT_TYPE = None
    log.info("email_dispatcher.skip_recurring_unregistered")

if RECURRING_EVENT_TYPE is not None:
    from app.services.email.renderers import recurring_invoice as recurring_renderer

    @projection(
        event_type=RECURRING_EVENT_TYPE,
        name="email_dispatcher_recurring_invoice_materialized",
        read_model_tables=READ_MODEL_TABLES,
    )
    async def on_recurring_invoice_materialized(event: Event, session: AsyncSession) -> None:
        payload = event.payload or {}
        # Only auto-issued recurring invoices trigger the email.
        if not payload.get("auto_issue"):
            return
        invoice_id_raw = payload.get("invoice_id")
        customer_id_raw = payload.get("customer_id")
        if not invoice_id_raw or not customer_id_raw:
            return
        invoice_id = uuid.UUID(str(invoice_id_raw))
        customer_id = uuid.UUID(str(customer_id_raw))
        to_address = await _to_customer_email(customer_id, session)
        if not to_address:
            return
        rendered = await recurring_renderer.render(invoice_id, session=session)
        await enqueue_email(
            EmailKind.RECURRING_INVOICE,
            subject_kind="recurring_invoice",
            subject_id=invoice_id,
            to_address=to_address,
            subject=rendered.subject,
            body_html=rendered.body_html,
            body_text=rendered.body_text,
            attachments=rendered.attachments,
            session=session,
        )
