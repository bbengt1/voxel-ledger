"""Credit note issue enqueues a QBO CreditMemo + apply drops outstanding
(Phase 7.4, #112; QBO-only per epic #312 Phase 5e)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.invoice import Invoice, InvoiceState
from app.models.qbo_sync_outbox import QboSyncOutbox
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
async def test_issue_credit_note_enqueues_qbo_credit_memo(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
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
    # QBO is the sole ledger (epic #312, Phase 5e): no local JE is stamped;
    # a native QBO CreditMemo is pushed via the sync outbox instead.
    assert r.json()["posting_journal_entry_id"] is None

    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "credit_note",
                QboSyncOutbox.local_id == uuid.UUID(note_id),
            )
        )
    ).scalar_one()
    assert outbox_row.op == "post"
    assert Decimal(outbox_row.payload["amount"]) == Decimal("20.00")
    assert outbox_row.payload["customer_id"] == str(customer.id)

    # Apply reduces outstanding without a real payment
    r = await client.post(f"/api/v1/credit-notes/{note_id}/apply", headers=auth_header(owner))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "applied"

    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.amount_outstanding == Decimal("80.000000")
    assert inv.state == InvoiceState.PARTIALLY_PAID
