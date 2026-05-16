"""Invoices CRUD + role matrix (Phase 7.3, #111)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import (
    auth_header,
    sample_invoice_body,
    seed_ar_posting_defaults,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_create_get_list_invoice(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    r = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["invoice_number"].startswith("INV-")
    assert inv["state"] == "draft"
    assert inv["total_amount"] == "20.000000"
    assert inv["posting_journal_entry_id"] is None
    assert len(inv["items"]) == 1

    # GET single
    r2 = await client.get(f"/api/v1/invoices/{inv['id']}", headers=auth_header(owner))
    assert r2.status_code == 200
    assert r2.json()["invoice_number"] == inv["invoice_number"]

    # LIST
    r3 = await client.get("/api/v1/invoices", headers=auth_header(owner))
    assert r3.status_code == 200
    items = r3.json()["items"]
    assert any(i["id"] == inv["id"] for i in items)


@pytest.mark.asyncio
async def test_update_only_legal_in_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]

    # Update draft is fine
    upd = await client.patch(
        f"/api/v1/invoices/{invoice_id}",
        headers=auth_header(owner),
        json={"notes": "updated"},
    )
    assert upd.status_code == 200
    assert upd.json()["notes"] == "updated"

    # Issue the invoice
    issued = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    assert issued.json()["state"] == "issued"

    # Now update should 400
    upd2 = await client.patch(
        f"/api/v1/invoices/{invoice_id}",
        headers=auth_header(owner),
        json={"notes": "after-issue"},
    )
    assert upd2.status_code == 400


@pytest.mark.asyncio
async def test_viewer_can_read_but_not_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]
    viewer = await token_for(Role.VIEWER, client, app_session)

    r_get = await client.get(f"/api/v1/invoices/{invoice_id}", headers=auth_header(viewer))
    assert r_get.status_code == 200

    r_post = await client.post(
        "/api/v1/invoices",
        headers=auth_header(viewer),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    assert r_post.status_code == 403

    r_issue = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(viewer))
    assert r_issue.status_code == 403


@pytest.mark.asyncio
async def test_production_role_cannot_write(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    prod = await token_for(Role.PRODUCTION, client, app_session)
    r = await client.post(
        "/api/v1/invoices",
        headers=auth_header(prod),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    assert r.status_code == 403
