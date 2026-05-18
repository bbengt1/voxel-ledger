"""CRUD smoke for tax profiles + rates (Phase 9.5, #157)."""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import auth_header, token_for
from tests._tax_helpers import seed_liability_account


@pytest.mark.asyncio
async def test_create_profile_and_rate(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    acct = await seed_liability_account(app_session)
    await app_session.commit()

    r = await client.post(
        "/api/v1/tax-profiles",
        headers=auth_header(owner),
        json={
            "code": "US-CA",
            "name": "California",
            "jurisdiction": "US-CA",
        },
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]

    # Add a rate
    rr = await client.post(
        f"/api/v1/tax-profiles/{profile_id}/rates",
        headers=auth_header(owner),
        json={
            "ordinal": 0,
            "name": "Sales",
            "rate": "0.075",
            "liability_account_id": str(acct.id),
            "compound_on_previous": False,
        },
    )
    assert rr.status_code == 201, rr.text
    rate_id = rr.json()["id"]

    # Fetch profile with rates
    g = await client.get(f"/api/v1/tax-profiles/{profile_id}", headers=auth_header(owner))
    assert g.status_code == 200
    body = g.json()
    assert body["code"] == "US-CA"
    assert len(body["rates"]) == 1
    assert body["rates"][0]["id"] == rate_id

    # Archive
    a = await client.post(f"/api/v1/tax-profiles/{profile_id}/archive", headers=auth_header(owner))
    assert a.status_code == 200
    assert a.json()["is_active"] is False

    # List with active=true should omit it
    listing = await client.get(
        "/api/v1/tax-profiles",
        headers=auth_header(owner),
        params={"active": "true"},
    )
    assert listing.status_code == 200
    ids = [p["id"] for p in listing.json()["items"]]
    assert profile_id not in ids


@pytest.mark.asyncio
async def test_duplicate_code_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)

    body = {"code": "X-DUP", "name": "X", "jurisdiction": "X"}
    r1 = await client.post("/api/v1/tax-profiles", headers=auth_header(owner), json=body)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/tax-profiles", headers=auth_header(owner), json=body)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_rate_account_must_be_liability(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    from app.models.account import Account

    owner = await token_for(Role.OWNER, client, app_session)
    asset_acct = Account(id=uuid.uuid4(), code="1100", name="Cash", type="asset")
    app_session.add(asset_acct)
    await app_session.commit()

    r = await client.post(
        "/api/v1/tax-profiles",
        headers=auth_header(owner),
        json={"code": "Y", "name": "Y", "jurisdiction": "Y"},
    )
    profile_id = r.json()["id"]

    rr = await client.post(
        f"/api/v1/tax-profiles/{profile_id}/rates",
        headers=auth_header(owner),
        json={
            "ordinal": 0,
            "name": "Bad",
            "rate": "0.05",
            "liability_account_id": str(asset_acct.id),
            "compound_on_previous": False,
        },
    )
    assert rr.status_code == 400
