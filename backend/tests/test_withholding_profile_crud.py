"""Withholding-profile CRUD smoke tests (Phase 9.7, #159)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import auth_header, token_for
from tests._withholding_helpers import seed_withholding_liability_account


@pytest.mark.asyncio
async def test_create_get_list_update_archive(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    liability = await seed_withholding_liability_account(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    create_body = {
        "code": "US-1099-NEC",
        "name": "1099-NEC backup withholding",
        "jurisdiction": "US",
        "rate": "0.07",
        "liability_account_id": str(liability.id),
        "threshold_per_year": "600.00",
        "form_kind": "1099-NEC",
    }
    create = await client.post(
        "/api/v1/withholding-profiles",
        headers=auth_header(owner),
        json=create_body,
    )
    assert create.status_code == 201, create.text
    profile_id = create.json()["id"]

    fetched = await client.get(
        f"/api/v1/withholding-profiles/{profile_id}", headers=auth_header(owner)
    )
    assert fetched.status_code == 200
    assert fetched.json()["code"] == "US-1099-NEC"
    assert fetched.json()["is_active"] is True

    listed = await client.get(
        "/api/v1/withholding-profiles?active=true",
        headers=auth_header(owner),
    )
    assert listed.status_code == 200
    assert any(p["id"] == profile_id for p in listed.json()["items"])

    # PATCH rate
    patched = await client.patch(
        f"/api/v1/withholding-profiles/{profile_id}",
        headers=auth_header(owner),
        json={"rate": "0.10"},
    )
    assert patched.status_code == 200
    from decimal import Decimal as _D

    assert _D(patched.json()["rate"]) == _D("0.10")

    # Archive
    archived = await client.post(
        f"/api/v1/withholding-profiles/{profile_id}/archive",
        headers=auth_header(owner),
    )
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False


@pytest.mark.asyncio
async def test_duplicate_code_returns_409(client: AsyncClient, app_session: AsyncSession) -> None:
    liability = await seed_withholding_liability_account(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = {
        "code": "DUPE",
        "name": "x",
        "jurisdiction": "US",
        "rate": "0.05",
        "liability_account_id": str(liability.id),
    }
    first = await client.post("/api/v1/withholding-profiles", headers=auth_header(owner), json=body)
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/withholding-profiles", headers=auth_header(owner), json=body
    )
    assert second.status_code == 409
