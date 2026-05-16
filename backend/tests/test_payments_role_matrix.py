"""Role matrix for payments + credit/debit-notes endpoints (Phase 7.4, #112).

* write (record / apply / cancel): owner + bookkeeper + sales
* read: + viewer
* unapply, mark-bounced: bookkeeper ONLY
"""

from __future__ import annotations

import pytest
from app.models.auth import Role, User
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
async def test_viewer_can_read_but_not_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_full_ar_stack(app_session)
    viewer = await token_for(Role.VIEWER, client, app_session)
    customer = await seed_customer(app_session)

    # Viewer can list
    r = await client.get("/api/v1/payments", headers=auth_header(viewer))
    assert r.status_code == 200

    # Viewer cannot create
    r = await client.post(
        "/api/v1/payments",
        headers=auth_header(viewer),
        json={"customer_id": str(customer.id), "amount": "10.00", "method": "cash"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_sales_can_apply_but_not_unapply(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_full_ar_stack(app_session)
    sales = await token_for(Role.SALES, client, app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "sales@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="50.00"
    )

    r = await client.post(
        "/api/v1/payments",
        headers=auth_header(sales),
        json={"customer_id": str(customer.id), "amount": "50.00", "method": "cash"},
    )
    assert r.status_code == 201
    payment_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(sales),
        json={"applications": [{"invoice_id": str(invoice.id), "amount": "50.00"}]},
    )
    assert r.status_code == 200

    # Sales cannot unapply
    r = await client.post(f"/api/v1/payments/{payment_id}/unapply", headers=auth_header(sales))
    assert r.status_code == 403

    # Sales cannot mark-bounced
    r = await client.post(f"/api/v1/payments/{payment_id}/mark-bounced", headers=auth_header(sales))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_owner_blocked_from_unapply(client: AsyncClient, app_session: AsyncSession) -> None:
    """Bookkeeper-only for unapply / mark-bounced — even owner is denied."""
    await seed_full_ar_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="50.00"
    )

    r = await client.post(
        "/api/v1/payments",
        headers=auth_header(owner),
        json={"customer_id": str(customer.id), "amount": "50.00", "method": "cash"},
    )
    payment_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(owner),
        json={"applications": [{"invoice_id": str(invoice.id), "amount": "50.00"}]},
    )
    assert r.status_code == 200

    r = await client.post(f"/api/v1/payments/{payment_id}/unapply", headers=auth_header(owner))
    # Strict reading of the spec: bookkeeper-only.
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_viewer_blocked_from_credit_note_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_full_ar_stack(app_session)
    viewer = await token_for(Role.VIEWER, client, app_session)
    sales = await token_for(Role.SALES, client, app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "sales@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="100.00"
    )

    # Viewer denied
    r = await client.post(
        "/api/v1/credit-notes",
        headers=auth_header(viewer),
        json={
            "invoice_id": str(invoice.id),
            "total_amount": "10.00",
        },
    )
    assert r.status_code == 403

    # Viewer can read
    r = await client.get("/api/v1/credit-notes", headers=auth_header(viewer))
    assert r.status_code == 200

    # Sales can write
    r = await client.post(
        "/api/v1/credit-notes",
        headers=auth_header(sales),
        json={
            "invoice_id": str(invoice.id),
            "total_amount": "10.00",
        },
    )
    assert r.status_code == 201
