"""Quote expire transition gating (Phase 7.2, #110).

Expire is only legal from ``sent``. A Phase 7.5/7.6 sweeper will
eventually call this once ``valid_until < now()``, but for now we expose
the manual transition and the state machine guards it.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._quotes_helpers import auth_header, sample_quote_body, seed_customer, token_for


@pytest.mark.asyncio
async def test_cannot_expire_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    r = await client.post(f"/api/v1/quotes/{quote_id}/expire", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_can_expire_sent(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    r = await client.post(f"/api/v1/quotes/{quote_id}/expire", headers=auth_header(owner))
    assert r.status_code == 200 and r.json()["state"] == "expired"


@pytest.mark.asyncio
async def test_cannot_expire_accepted(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))
    r = await client.post(f"/api/v1/quotes/{quote_id}/expire", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_expire_twice(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    r1 = await client.post(f"/api/v1/quotes/{quote_id}/expire", headers=auth_header(owner))
    assert r1.status_code == 200
    r2 = await client.post(f"/api/v1/quotes/{quote_id}/expire", headers=auth_header(owner))
    assert r2.status_code == 400
