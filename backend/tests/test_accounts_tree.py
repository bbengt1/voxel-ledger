"""``GET /accounts/tree`` returns the nested hierarchy (Phase 4.1)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_token(client: AsyncClient, session: AsyncSession) -> str:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_tree_returns_nested_structure(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    # Two top-levels (Assets, Liabilities) with children.
    a = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    aid = a.json()["id"]
    await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1010", "name": "Cash", "type": "asset", "parent_account_id": aid},
    )
    await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1020", "name": "AR", "type": "asset", "parent_account_id": aid},
    )
    await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "2000", "name": "Liabilities", "type": "liability"},
    )

    r = await client.get("/api/v1/accounts/tree", headers=_h(token))
    assert r.status_code == 200
    items = r.json()["items"]
    by_code = {item["code"]: item for item in items}
    assert "1000" in by_code
    assert "2000" in by_code
    cash_codes = sorted(c["code"] for c in by_code["1000"]["children"])
    assert cash_codes == ["1010", "1020"]
    assert by_code["2000"]["children"] == []


@pytest.mark.asyncio
async def test_tree_excludes_archived_by_default(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    parent = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    pid = parent.json()["id"]
    child = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1010", "name": "Cash", "type": "asset", "parent_account_id": pid},
    )
    cid = child.json()["id"]
    await client.post(f"/api/v1/accounts/{cid}/archive", headers=_h(token))

    r = await client.get("/api/v1/accounts/tree", headers=_h(token))
    by_code = {item["code"]: item for item in r.json()["items"]}
    assert by_code["1000"]["children"] == []

    r = await client.get("/api/v1/accounts/tree?include_archived=true", headers=_h(token))
    by_code = {item["code"]: item for item in r.json()["items"]}
    assert [c["code"] for c in by_code["1000"]["children"]] == ["1010"]
