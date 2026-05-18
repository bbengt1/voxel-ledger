"""Expense category one-level hierarchy tests (Phase 8.6, #133)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_categories_helpers import auth_header, seed_expense_account, token_for


@pytest.mark.asyncio
async def test_child_under_root_succeeds(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)

    root = await client.post(
        "/api/v1/expense-categories",
        json={"code": "ROOT", "name": "Root", "default_expense_account_id": str(acct.id)},
        headers=auth_header(token),
    )
    root_id = root.json()["id"]

    child = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "CHILD",
            "name": "Child",
            "default_expense_account_id": str(acct.id),
            "parent_id": root_id,
        },
        headers=auth_header(token),
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == root_id


@pytest.mark.asyncio
async def test_grandchild_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)

    root = await client.post(
        "/api/v1/expense-categories",
        json={"code": "ROOT2", "name": "Root2", "default_expense_account_id": str(acct.id)},
        headers=auth_header(token),
    )
    root_id = root.json()["id"]

    child = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "CHILD2",
            "name": "Child2",
            "default_expense_account_id": str(acct.id),
            "parent_id": root_id,
        },
        headers=auth_header(token),
    )
    child_id = child.json()["id"]

    grandchild = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "GRAND",
            "name": "Grand",
            "default_expense_account_id": str(acct.id),
            "parent_id": child_id,
        },
        headers=auth_header(token),
    )
    assert grandchild.status_code == 400
    assert "one level" in grandchild.json()["detail"]


@pytest.mark.asyncio
async def test_self_parent_blocked(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)
    r = await client.post(
        "/api/v1/expense-categories",
        json={"code": "X", "name": "X", "default_expense_account_id": str(acct.id)},
        headers=auth_header(token),
    )
    cid = r.json()["id"]
    r2 = await client.patch(
        f"/api/v1/expense-categories/{cid}",
        json={"parent_id": cid},
        headers=auth_header(token),
    )
    assert r2.status_code == 400
    assert "self" in r2.json()["detail"]
