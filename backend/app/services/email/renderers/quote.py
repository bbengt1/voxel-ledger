"""Quote renderer (Phase 7.7, #115)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.quote import Quote
from app.services.email.providers import Attachment
from app.services.email.renderers import Rendered, get_template


async def render(
    quote_id: uuid.UUID,
    *,
    session: AsyncSession,
    attach_pdf: bool = True,
) -> Rendered:
    quote = (await session.execute(select(Quote).where(Quote.id == quote_id))).scalar_one_or_none()
    if quote is None:
        raise ValueError(f"quote {quote_id} not found")
    customer = (
        await session.execute(select(Customer).where(Customer.id == quote.customer_id))
    ).scalar_one_or_none()

    customer_name = customer.display_name if customer else "Customer"

    subject = f"Quote {quote.quote_number}"
    template = get_template("quote.html")
    body_html = template.render(
        customer_name=customer_name,
        quote_number=quote.quote_number,
        total_amount=str(quote.total_amount),
        currency=getattr(quote, "currency", "USD"),
        valid_until=quote.valid_until.date().isoformat() if quote.valid_until else None,
    )

    attachments: list[Attachment] = []
    if attach_pdf:
        attachments.append(
            Attachment(
                filename=f"{quote.quote_number}.pdf",
                content=_render_quote_pdf_bytes(quote),
                content_type="application/pdf",
            )
        )

    body_text = f"Quote {quote.quote_number}\n" f"Total: {quote.total_amount}\n"

    return Rendered(
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        attachments=attachments,
    )


def _render_quote_pdf_bytes(quote: Quote) -> bytes:
    """Minimal one-page PDF placeholder via reportlab."""
    import io

    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    margin = 0.5 * inch
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, height - margin, f"QUOTE {quote.quote_number}")
    c.setFont("Helvetica", 11)
    c.drawString(margin, height - margin - 0.4 * inch, f"Total: {quote.total_amount}")
    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = ["render"]
