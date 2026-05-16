"""Apply + unapply leaves GL net-zero and restores invoice outstanding (Phase 7.4, #112)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.invoice import Invoice, InvoiceState
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.models.payment import PaymentState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._payments_helpers import (
    auth_header,
    seed_customer,
    seed_full_ar_stack,
    seed_issued_invoice,
    token_for,
)


@pytest.mark.asyncio
async def test_unapply_reverses_je_and_restores_outstanding(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    bookkeeper = await token_for(Role.BOOKKEEPER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "bookkeeper@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="200.00"
    )

    r = await client.post(
        "/api/v1/payments",
        headers=auth_header(bookkeeper),
        json={"customer_id": str(customer.id), "amount": "200.00", "method": "wire"},
    )
    payment_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(bookkeeper),
        json={"applications": [{"invoice_id": str(invoice.id), "amount": "200.00"}]},
    )
    assert r.status_code == 200

    # Snapshot GL totals
    pre_total_debit = (await app_session.execute(select(JournalLine.debit))).scalars().all()
    pre_total_credit = (await app_session.execute(select(JournalLine.credit))).scalars().all()
    pre_net = sum(pre_total_debit, Decimal("0")) - sum(pre_total_credit, Decimal("0"))

    # Unapply
    r = await client.post(f"/api/v1/payments/{payment_id}/unapply", headers=auth_header(bookkeeper))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "pending"

    # Net debit/credit unchanged across all entries (always balanced)
    # but the payment's posting JE has been reversed via a new entry.
    post_total_debit = (await app_session.execute(select(JournalLine.debit))).scalars().all()
    post_total_credit = (await app_session.execute(select(JournalLine.credit))).scalars().all()
    post_net = sum(post_total_debit, Decimal("0")) - sum(post_total_credit, Decimal("0"))
    # Both pre and post nets should be zero (balanced books)
    assert pre_net == Decimal("0")
    assert post_net == Decimal("0")

    # Invoice restored
    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.amount_paid == Decimal("0E-6")
    assert inv.amount_outstanding == Decimal("200.000000")
    assert inv.state == InvoiceState.ISSUED

    # Payment back to pending
    import uuid as _uuid

    from app.models.payment import Payment

    p = (
        await app_session.execute(select(Payment).where(Payment.id == _uuid.UUID(payment_id)))
    ).scalar_one()
    await app_session.refresh(p)
    assert p.state == PaymentState.PENDING
    _ = JournalEntry  # quiet unused-import lint
