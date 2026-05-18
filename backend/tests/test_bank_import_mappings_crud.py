"""Bank import mapping CRUD smoke tests (Phase 8.9, #136)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import auth_header, seed_bank_account, token_for


@pytest.mark.asyncio
async def test_create_get_patch_deactivate(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_bank_account(app_session)

    r = await client.post(
        "/api/v1/bank-import-mappings",
        json={
            "name": "wells-signed",
            "account_id": str(acct.id),
            "file_kind": "csv",
            "column_map": {
                "date": "Date",
                "description": "Description",
                "amount": "Amount",
            },
            "date_format": "%Y-%m-%d",
            "amount_sign": "signed_amount",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "wells-signed"
    assert body["is_active"] is True
    mid = body["id"]

    r2 = await client.get(f"/api/v1/bank-import-mappings/{mid}", headers=auth_header(token))
    assert r2.status_code == 200

    r3 = await client.patch(
        f"/api/v1/bank-import-mappings/{mid}",
        json={"notes": "spreadsheet export from wells fargo"},
        headers=auth_header(token),
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["notes"] == "spreadsheet export from wells fargo"

    r4 = await client.post(
        f"/api/v1/bank-import-mappings/{mid}/deactivate", headers=auth_header(token)
    )
    assert r4.status_code == 200
    assert r4.json()["is_active"] is False


@pytest.mark.asyncio
async def test_duplicate_name_per_account_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_bank_account(app_session)
    body = {
        "name": "dup",
        "account_id": str(acct.id),
        "file_kind": "csv",
        "column_map": {"date": "Date", "description": "Desc", "amount": "Amount"},
        "amount_sign": "signed_amount",
    }
    r1 = await client.post("/api/v1/bank-import-mappings", json=body, headers=auth_header(token))
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/bank-import-mappings", json=body, headers=auth_header(token))
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_list_filters(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_bank_account(app_session)
    for name in ("a", "b", "c"):
        await client.post(
            "/api/v1/bank-import-mappings",
            json={
                "name": name,
                "account_id": str(acct.id),
                "file_kind": "csv",
                "column_map": {"date": "Date", "description": "D", "amount": "A"},
                "amount_sign": "signed_amount",
            },
            headers=auth_header(token),
        )
    r = await client.get(
        "/api/v1/bank-import-mappings",
        params={"account_id": str(acct.id)},
        headers=auth_header(token),
    )
    assert {i["name"] for i in r.json()["items"]} == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_viewer_cannot_create(client: AsyncClient, app_session: AsyncSession) -> None:
    viewer = await token_for(Role.VIEWER, client, app_session)
    acct = await seed_bank_account(app_session)
    r = await client.post(
        "/api/v1/bank-import-mappings",
        json={
            "name": "x",
            "account_id": str(acct.id),
            "file_kind": "csv",
            "column_map": {"date": "Date", "description": "D", "amount": "A"},
            "amount_sign": "signed_amount",
        },
        headers=auth_header(viewer),
    )
    assert r.status_code == 403
