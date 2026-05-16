"""Credit note proportional revenue reversal + apply drops outstanding (Phase 7.4, #112)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.invoice import Invoice, InvoiceState
from app.models.journal_entry import JournalEntry
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
async def test_issue_credit_note_posts_debit_revenue_credit_ar(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="100.00"
    )

    r = await client.post(
        "/api/v1/credit-notes",
        headers=auth_header(owner),
        json={
            "invoice_id": str(invoice.id),
            "total_amount": "20.00",
            "reason": "discount",
        },
    )
    assert r.status_code == 201, r.text
    note_id = r.json()["id"]

    r = await client.post(f"/api/v1/credit-notes/{note_id}/issue", headers=auth_header(owner))
    assert r.status_code == 200
    je_id = uuid.UUID(r.json()["posting_journal_entry_id"])

    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    by_acct = {line.account_id: line for line in je.lines}
    # Debit revenue, credit AR -> reverses a slice of original revenue posting
    assert by_acct[accounts["revenue_account_id"]].debit == Decimal("20.000000")
    assert by_acct[accounts["ar_account_id"]].credit == Decimal("20.000000")

    # Apply reduces outstanding without a real payment
    r = await client.post(f"/api/v1/credit-notes/{note_id}/apply", headers=auth_header(owner))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "applied"

    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.amount_outstanding == Decimal("80.000000")
    assert inv.state == InvoiceState.PARTIALLY_PAID
