"""Invoice renderer (Phase 7.7, #115)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.services.email.providers import Attachment
from app.services.email.renderers import Rendered, get_template


async def render(
    invoice_id: uuid.UUID,
    *,
    session: AsyncSession,
    attach_pdf: bool = True,
) -> Rendered:
    invoice = (
        await session.execute(
            select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.items))
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise ValueError(f"invoice {invoice_id} not found")
    customer = (
        await session.execute(select(Customer).where(Customer.id == invoice.customer_id))
    ).scalar_one_or_none()

    customer_name = customer.display_name if customer else "Customer"

    subject = f"Invoice {invoice.invoice_number}"
    template = get_template("invoice.html")
    body_html = template.render(
        customer_name=customer_name,
        invoice_number=invoice.invoice_number,
        total_amount=str(invoice.total_amount),
        currency=invoice.currency,
        due_at=invoice.due_at.date().isoformat() if invoice.due_at else None,
    )

    attachments: list[Attachment] = []
    if attach_pdf:
        attachments.append(
            Attachment(
                filename=f"{invoice.invoice_number}.pdf",
                content=_render_invoice_pdf_bytes(invoice),
                content_type="application/pdf",
            )
        )

    body_text = (
        f"Invoice {invoice.invoice_number}\n" f"Total: {invoice.total_amount} {invoice.currency}\n"
    )

    return Rendered(
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        attachments=attachments,
    )


def _render_invoice_pdf_bytes(invoice: Invoice) -> bytes:
    import io

    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    margin = 0.5 * inch
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, height - margin, f"INVOICE {invoice.invoice_number}")
    c.setFont("Helvetica", 11)
    c.drawString(margin, height - margin - 0.4 * inch, f"Total: {invoice.total_amount}")
    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = ["render"]
