"""Account hierarchy cycle detection (Phase 4.1, headline test)."""

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
async def test_three_node_cycle_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    """A -> B -> C; attempt to PATCH A.parent = C should 400."""
    token = await _owner_token(client, app_session)
    a = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "A", "type": "asset"},
    )
    aid = a.json()["id"]
    b = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1100", "name": "B", "type": "asset", "parent_account_id": aid},
    )
    bid = b.json()["id"]
    c = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1110", "name": "C", "type": "asset", "parent_account_id": bid},
    )
    cid = c.json()["id"]

    r = await client.patch(
        f"/api/v1/accounts/{aid}",
        headers=_h(token),
        json={"parent_account_id": cid},
    )
    assert r.status_code == 400, r.text
    assert "cycle" in r.text.lower()


@pytest.mark.asyncio
async def test_self_reference_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _owner_token(client, app_session)
    a = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "A", "type": "asset"},
    )
    aid = a.json()["id"]
    r = await client.patch(
        f"/api/v1/accounts/{aid}",
        headers=_h(token),
        json={"parent_account_id": aid},
    )
    assert r.status_code == 400
    assert "cycle" in r.text.lower() or "own parent" in r.text.lower()


@pytest.mark.asyncio
async def test_reparent_to_unrelated_node_succeeds(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Sanity: legitimate reparenting works."""
    token = await _owner_token(client, app_session)
    a = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "A", "type": "asset"},
    )
    aid = a.json()["id"]
    b = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1100", "name": "B", "type": "asset"},
    )
    bid = b.json()["id"]
    c = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1200", "name": "C", "type": "asset", "parent_account_id": aid},
    )
    cid = c.json()["id"]
    r = await client.patch(
        f"/api/v1/accounts/{cid}",
        headers=_h(token),
        json={"parent_account_id": bid},
    )
    assert r.status_code == 200
    assert r.json()["parent_account_id"] == bid
