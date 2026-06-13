"""Single-invoice payment apply drops outstanding to 0, invoice -> paid
(Phase 7.4, #112).

QBO is the sole ledger (epic #312, Phase 5e): the apply enqueues a
native QBO Payment via the sync outbox instead of posting a local JE;
``posting_journal_entry_id`` is always ``None``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.invoice import Invoice, InvoiceState
from app.models.payment import Payment, PaymentState
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
async def test_apply_full_payment_marks_invoice_paid(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)

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
    # QBO is the sole ledger: no local JE.
    assert body["posting_journal_entry_id"] is None

    # Invoice now paid
    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.amount_paid == Decimal("100.000000")
    assert inv.amount_outstanding == Decimal("0E-6")
    assert inv.state == InvoiceState.PAID

    # A QBO outbox row was enqueued for the payment instead of a local JE.
    outbox = (
        (
            await app_session.execute(
                select(QboSyncOutbox).where(
                    QboSyncOutbox.kind == "payment",
                    QboSyncOutbox.local_id == uuid.UUID(payment_id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox) == 1
    assert outbox[0].op == "post"

    # Payment state
    p = (
        await app_session.execute(select(Payment).where(Payment.id == uuid.UUID(payment_id)))
    ).scalar_one()
    await app_session.refresh(p)
    assert p.state == PaymentState.APPLIED
