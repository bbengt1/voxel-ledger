"""Statement renderer (Phase 7.7, #115).

Digests a customer's outstanding (and optionally paid) invoices into a
single email. Driven by ``POST /customers/{id}/statements/send`` and
potentially future recurring-statement automation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceState
from app.services.email.renderers import Rendered, get_template


async def render(
    customer_id: uuid.UUID,
    *,
    session: AsyncSession,
    include_paid: bool = False,
) -> Rendered:
    customer = (
        await session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if customer is None:
        raise ValueError(f"customer {customer_id} not found")

    stmt = (
        select(Invoice)
        .where(Invoice.customer_id == customer_id)
        .order_by(Invoice.issued_at.desc().nullslast())
    )
    rows = list((await session.execute(stmt)).scalars().all())

    UNPAID = {
        InvoiceState.ISSUED,
        InvoiceState.PARTIALLY_PAID,
        InvoiceState.OVERDUE,
    }
    selected: list[Invoice] = []
    total_outstanding = Decimal("0")
    for inv in rows:
        if inv.state in UNPAID or (include_paid and inv.state == InvoiceState.PAID):
            selected.append(inv)
            total_outstanding += Decimal(str(inv.amount_outstanding))

    as_of = datetime.now(UTC).date().isoformat()
    subject = f"Account statement for {customer.display_name} as of {as_of}"

    template = get_template("statement.html")
    body_html = template.render(
        customer_name=customer.display_name,
        as_of=as_of,
        invoices=[
            {
                "invoice_number": inv.invoice_number,
                "issued_at": inv.issued_at.date().isoformat() if inv.issued_at else "",
                "due_at": inv.due_at.date().isoformat() if inv.due_at else "",
                "total_amount": str(inv.total_amount),
                "amount_outstanding": str(inv.amount_outstanding),
                "state": inv.state.value if hasattr(inv.state, "value") else str(inv.state),
            }
            for inv in selected
        ],
        total_outstanding=str(total_outstanding),
        currency="USD",
    )
    body_text_lines = [f"Statement for {customer.display_name} as of {as_of}", ""]
    for inv in selected:
        body_text_lines.append(
            f"  {inv.invoice_number}: total {inv.total_amount}, "
            f"outstanding {inv.amount_outstanding}"
        )
    body_text_lines.append("")
    body_text_lines.append(f"Total outstanding: {total_outstanding}")
    body_text = "\n".join(body_text_lines)

    return Rendered(
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        attachments=[],
    )


__all__ = ["render"]
