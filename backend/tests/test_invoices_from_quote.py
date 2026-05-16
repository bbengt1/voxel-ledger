"""Quote -> invoice conversion (Phase 7.3, #111).

Replaces the Phase 7.2 stub assertion (501) with the real flow:
``POST /api/v1/quotes/{id}/convert-to-invoice`` returns 201 with
``{"invoice_id": "..."}``; the quote stays in ``accepted`` and gains an
``accepted_invoice_id`` FK; the invoice carries the line items.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import (
    auth_header,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_convert_quote_to_invoice_full_flow(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    items = [
        {
            "kind": "manual",
            "description": "Widget A",
            "quantity": "2",
            "unit_price": "10.00",
        },
        {
            "kind": "manual",
            "description": "Widget B",
            "quantity": "1",
            "unit_price": "5.00",
        },
    ]
    quote = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json={"customer_id": str(customer.id), "items": items},
    )
    assert quote.status_code == 201, quote.text
    quote_id = quote.json()["id"]

    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))

    conv = await client.post(
        f"/api/v1/quotes/{quote_id}/convert-to-invoice", headers=auth_header(owner)
    )
    assert conv.status_code == 201, conv.text
    invoice_id = conv.json()["invoice_id"]
    assert invoice_id

    # Quote shows accepted_invoice_id populated; state is still accepted.
    q2 = await client.get(f"/api/v1/quotes/{quote_id}", headers=auth_header(owner))
    body = q2.json()
    assert body["state"] == "accepted"
    assert body["accepted_invoice_id"] == invoice_id

    # Invoice has copied lines + customer.
    inv = await client.get(f"/api/v1/invoices/{invoice_id}", headers=auth_header(owner))
    inv_body = inv.json()
    assert inv_body["state"] == "draft"
    assert inv_body["customer_id"] == str(customer.id)
    assert inv_body["quote_id"] == quote_id
    assert len(inv_body["items"]) == 2
    descriptions = sorted(item["description"] for item in inv_body["items"])
    assert descriptions == ["Widget A", "Widget B"]


@pytest.mark.asyncio
async def test_convert_unaccepted_quote_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    quote = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json={
            "customer_id": str(customer.id),
            "items": [
                {
                    "kind": "manual",
                    "description": "x",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
        },
    )
    quote_id = quote.json()["id"]
    # Not sent / not accepted — convert should 400.
    r = await client.post(
        f"/api/v1/quotes/{quote_id}/convert-to-invoice", headers=auth_header(owner)
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_convert_unknown_quote_returns_404(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/quotes/00000000-0000-0000-0000-000000000000/convert-to-invoice",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_convert_requires_write_role(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    quote = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json={
            "customer_id": str(customer.id),
            "items": [
                {
                    "kind": "manual",
                    "description": "x",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
        },
    )
    quote_id = quote.json()["id"]
    viewer = await token_for(Role.VIEWER, client, app_session)
    r = await client.post(
        f"/api/v1/quotes/{quote_id}/convert-to-invoice", headers=auth_header(viewer)
    )
    assert r.status_code == 403
