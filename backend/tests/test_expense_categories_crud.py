"""Expense categories CRUD tests (Phase 8.6, #133)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_categories_helpers import (
    auth_header,
    seed_expense_account,
    seed_non_expense_account,
    token_for,
)


@pytest.mark.asyncio
async def test_create_and_get_round_trip(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)

    r = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "OFFICE_SUPPLIES",
            "name": "Office Supplies",
            "default_expense_account_id": str(acct.id),
            "notes": "small consumables",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "OFFICE_SUPPLIES"
    assert body["is_active"] is True
    cid = body["id"]

    r2 = await client.get(f"/api/v1/expense-categories/{cid}", headers=auth_header(token))
    assert r2.status_code == 200
    assert r2.json()["id"] == cid


@pytest.mark.asyncio
async def test_create_rejects_non_expense_account(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    asset = await seed_non_expense_account(app_session)

    r = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "BAD",
            "name": "Bad",
            "default_expense_account_id": str(asset.id),
        },
        headers=auth_header(token),
    )
    assert r.status_code == 400
    assert "expense" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_duplicate_code_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)
    body = {
        "code": "RENT",
        "name": "Rent",
        "default_expense_account_id": str(acct.id),
    }
    r1 = await client.post("/api/v1/expense-categories", json=body, headers=auth_header(token))
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/expense-categories", json=body, headers=auth_header(token))
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_patch_updates_fields(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)
    r = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "TRAVEL",
            "name": "Travel",
            "default_expense_account_id": str(acct.id),
        },
        headers=auth_header(token),
    )
    cid = r.json()["id"]

    r2 = await client.patch(
        f"/api/v1/expense-categories/{cid}",
        json={"name": "Business Travel", "notes": "operator-only memo"},
        headers=auth_header(token),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["name"] == "Business Travel"
    assert r2.json()["notes"] == "operator-only memo"


@pytest.mark.asyncio
async def test_archive_via_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)
    r = await client.post(
        "/api/v1/expense-categories",
        json={"code": "MEALS", "name": "Meals", "default_expense_account_id": str(acct.id)},
        headers=auth_header(token),
    )
    cid = r.json()["id"]
    r2 = await client.post(f"/api/v1/expense-categories/{cid}/archive", headers=auth_header(token))
    assert r2.status_code == 200
    assert r2.json()["is_active"] is False


@pytest.mark.asyncio
async def test_list_filters(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)
    for code in ("AAA", "BBB", "CCC"):
        await client.post(
            "/api/v1/expense-categories",
            json={"code": code, "name": code, "default_expense_account_id": str(acct.id)},
            headers=auth_header(token),
        )
    # archive one
    list_r = await client.get("/api/v1/expense-categories", headers=auth_header(token))
    aaa_id = next(i["id"] for i in list_r.json()["items"] if i["code"] == "AAA")
    await client.post(f"/api/v1/expense-categories/{aaa_id}/archive", headers=auth_header(token))

    active_only = await client.get(
        "/api/v1/expense-categories", params={"active": "true"}, headers=auth_header(token)
    )
    codes = {i["code"] for i in active_only.json()["items"]}
    assert "AAA" not in codes
    assert {"BBB", "CCC"}.issubset(codes)

    searched = await client.get(
        "/api/v1/expense-categories", params={"search": "bbb"}, headers=auth_header(token)
    )
    assert {i["code"] for i in searched.json()["items"]} == {"BBB"}


@pytest.mark.asyncio
async def test_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    bookkeeper = await token_for(Role.BOOKKEEPER, client, app_session)
    viewer = await token_for(Role.VIEWER, client, app_session)
    acct = await seed_expense_account(app_session)

    # Viewer cannot create.
    r = await client.post(
        "/api/v1/expense-categories",
        json={"code": "X", "name": "X", "default_expense_account_id": str(acct.id)},
        headers=auth_header(viewer),
    )
    assert r.status_code == 403

    # Bookkeeper can create.
    r = await client.post(
        "/api/v1/expense-categories",
        json={"code": "Y", "name": "Y", "default_expense_account_id": str(acct.id)},
        headers=auth_header(bookkeeper),
    )
    assert r.status_code == 201

    # Viewer can list.
    r2 = await client.get("/api/v1/expense-categories", headers=auth_header(viewer))
    assert r2.status_code == 200
