"""Single-invoice payment posts AR/Bank JE, drops outstanding to 0,
invoice -> paid (Phase 7.4, #112)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.invoice import Invoice, InvoiceState
from app.models.journal_entry import JournalEntry
from app.models.payment import Payment, PaymentState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._payments_helpers import (
    auth_header,
    seed_customer,
    seed_full_ar_stack,
    seed_issued_invoice,
    token_for,
)


@pytest.mark.asyncio
async def test_apply_full_payment_marks_invoice_paid(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    owner_user_id = (
        await app_session.execute(select(Invoice.created_by_user_id).limit(1))
    ).scalar_one_or_none()

    # Resolve owner user id
    from app.models.auth import User

    user_row = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user_row.id, unit_price="100.00"
    )
    assert invoice.amount_outstanding == Decimal("100.000000")

    # Record payment
    body = {
        "customer_id": str(customer.id),
        "amount": "100.00",
        "method": "ach",
    }
    r = await client.post("/api/v1/payments", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payment_id = r.json()["id"]
    assert r.json()["state"] == "pending"

    # Apply to invoice
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(owner),
        json={"applications": [{"invoice_id": str(invoice.id), "amount": "100.00"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "applied"
    assert body["posting_journal_entry_id"] is not None

    # Invoice now paid
    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.amount_paid == Decimal("100.000000")
    assert inv.amount_outstanding == Decimal("0E-6")
    assert inv.state == InvoiceState.PAID

    # JE has bank debit + AR credit
    je_id = uuid.UUID(body["posting_journal_entry_id"])
    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    by_acct = {line.account_id: line for line in je.lines}
    assert by_acct[accounts["bank_account_id"]].debit == Decimal("100.000000")
    assert by_acct[accounts["ar_account_id"]].credit == Decimal("100.000000")

    # Payment state
    p = (
        await app_session.execute(select(Payment).where(Payment.id == uuid.UUID(payment_id)))
    ).scalar_one()
    await app_session.refresh(p)
    assert p.state == PaymentState.APPLIED
    # Suppress unused
    _ = owner_user_id
