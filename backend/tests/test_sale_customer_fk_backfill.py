"""Sale + POS cart ``customer_id`` FK backfill (Phase 7.1, #109).

Verifies that sales can be created with OR without ``customer_id``; the
column stays null on legacy / POS-walk-in rows and is set when a real
customer is selected.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._customers_helpers import auth_header, token_for
from tests._sales_helpers import sample_sale_body, seed_channel


async def _create_customer(client: AsyncClient, token: str) -> str:
    r = await client.post(
        "/api/v1/customers",
        json={"display_name": "Acme Co."},
        headers=auth_header(token),
    )
    return r.json()["id"]


@pytest.mark.asyncio
async def test_create_sale_without_customer_id(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    channel = await seed_channel(app_session)
    body = sample_sale_body(channel_id=str(channel.id))
    r = await client.post("/api/v1/sales", json=body, headers=auth_header(token))
    assert r.status_code == 201, r.text
    assert r.json()["customer_id"] is None


@pytest.mark.asyncio
async def test_create_sale_with_customer_id(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    channel = await seed_channel(app_session)
    customer_id = await _create_customer(client, token)
    body = sample_sale_body(channel_id=str(channel.id))
    body["customer_id"] = customer_id

    r = await client.post("/api/v1/sales", json=body, headers=auth_header(token))
    assert r.status_code == 201, r.text
    assert r.json()["customer_id"] == customer_id


@pytest.mark.asyncio
async def test_legacy_sale_rows_have_null_customer_id(
    client: AsyncClient, app_session: AsyncSession
):
    """The Phase 6 free-text snapshot fields stay required + the FK
    stays null when not supplied (POS walk-in equivalent)."""
    token = await token_for(Role.OWNER, client, app_session)
    channel = await seed_channel(app_session)
    body = sample_sale_body(channel_id=str(channel.id))
    body["customer_name"] = "Walk-in Customer"
    body["customer_email"] = None

    r = await client.post("/api/v1/sales", json=body, headers=auth_header(token))
    assert r.status_code == 201
    j = r.json()
    assert j["customer_name"] == "Walk-in Customer"
    assert j["customer_id"] is None


@pytest.mark.asyncio
async def test_pos_cart_accepts_customer_id(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    channel = await seed_channel(app_session)
    customer_id = await _create_customer(client, token)

    r = await client.post(
        "/api/v1/pos/carts",
        json={"channel_id": str(channel.id), "customer_id": customer_id},
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["customer_id"] == customer_id


@pytest.mark.asyncio
async def test_pos_cart_customer_id_optional(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    channel = await seed_channel(app_session)
    r = await client.post(
        "/api/v1/pos/carts",
        json={"channel_id": str(channel.id)},
        headers=auth_header(token),
    )
    assert r.status_code == 201
    assert r.json()["customer_id"] is None
