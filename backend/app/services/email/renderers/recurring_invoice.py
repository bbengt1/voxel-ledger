"""Recurring-invoice renderer (Phase 7.7, #115).

Thin wrapper over the invoice renderer — same template, different
trigger. Kept as its own module so the dispatcher can register it
distinctly under ``EmailKind.RECURRING_INVOICE``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email.renderers import Rendered
from app.services.email.renderers import invoice as invoice_renderer


async def render(
    invoice_id: uuid.UUID,
    *,
    session: AsyncSession,
    attach_pdf: bool = True,
) -> Rendered:
    rendered = await invoice_renderer.render(invoice_id, session=session, attach_pdf=attach_pdf)
    return Rendered(
        subject=f"[recurring] {rendered.subject}",
        body_html=rendered.body_html,
        body_text=rendered.body_text,
        attachments=rendered.attachments,
    )


__all__ = ["render"]
