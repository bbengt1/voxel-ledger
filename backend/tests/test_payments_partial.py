"""Partial application -> partially_paid; residue accrues to credit (Phase 7.4, #112)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.customer_credit import CustomerCreditBalance
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
async def test_partial_apply_drops_state_to_partially_paid(
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
        "/api/v1/payments",
        headers=auth_header(owner),
        json={"customer_id": str(customer.id), "amount": "60.00", "method": "cash"},
    )
    payment_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(owner),
        json={"applications": [{"invoice_id": str(invoice.id), "amount": "60.00"}]},
    )
    assert r.status_code == 200

    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.amount_outstanding == Decimal("40.000000")
    assert inv.state == InvoiceState.PARTIALLY_PAID


@pytest.mark.asyncio
async def test_overpayment_excess_to_credit(client: AsyncClient, app_session: AsyncSession) -> None:
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
        "/api/v1/payments",
        headers=auth_header(owner),
        json={"customer_id": str(customer.id), "amount": "150.00", "method": "ach"},
    )
    payment_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(owner),
        json={
            "applications": [{"invoice_id": str(invoice.id), "amount": "100.00"}],
            "apply_excess_to_credit": True,
        },
    )
    assert r.status_code == 200, r.text

    inv = (await app_session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    await app_session.refresh(inv)
    assert inv.state == InvoiceState.PAID
    assert inv.amount_outstanding == Decimal("0E-6")

    bal = (
        await app_session.execute(
            select(CustomerCreditBalance).where(CustomerCreditBalance.customer_id == customer.id)
        )
    ).scalar_one()
    assert bal.available_amount == Decimal("50.000000")


@pytest.mark.asyncio
async def test_overpayment_without_optin_is_rejected(
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
        "/api/v1/payments",
        headers=auth_header(owner),
        json={"customer_id": str(customer.id), "amount": "150.00", "method": "ach"},
    )
    payment_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(owner),
        json={
            "applications": [{"invoice_id": str(invoice.id), "amount": "100.00"}],
            "apply_excess_to_credit": False,
        },
    )
    assert r.status_code == 400
    assert "apply_excess_to_credit" in r.json()["detail"]
