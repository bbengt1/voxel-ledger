"""One payment applied across multiple invoices (Phase 7.4, #112)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.invoice import Invoice, InvoiceState
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
async def test_one_payment_across_two_invoices(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    inv1 = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="60.00"
    )
    inv2 = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="40.00"
    )

    r = await client.post(
        "/api/v1/payments",
        headers=auth_header(owner),
        json={"customer_id": str(customer.id), "amount": "100.00", "method": "check"},
    )
    payment_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(owner),
        json={
            "applications": [
                {"invoice_id": str(inv1.id), "amount": "60.00"},
                {"invoice_id": str(inv2.id), "amount": "40.00"},
            ]
        },
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert len(body["applications"]) == 2

    # Both invoices paid
    for inv_id in (inv1.id, inv2.id):
        inv = (await app_session.execute(select(Invoice).where(Invoice.id == inv_id))).scalar_one()
        await app_session.refresh(inv)
        assert inv.state == InvoiceState.PAID
        assert inv.amount_outstanding == Decimal("0E-6")
