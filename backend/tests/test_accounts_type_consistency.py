"""Parent and child accounts must share a ``type`` (Phase 4.1)."""

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
async def test_create_type_mismatch_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    liability_parent = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "2000", "name": "Liabilities", "type": "liability"},
    )
    pid = liability_parent.json()["id"]
    r = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={
            "code": "2100",
            "name": "Misplaced Asset",
            "type": "asset",
            "parent_account_id": pid,
        },
    )
    assert r.status_code == 400
    assert "type" in r.text.lower()


@pytest.mark.asyncio
async def test_reparent_type_mismatch_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    asset = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "Cash", "type": "asset"},
    )
    aid = asset.json()["id"]
    liab = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "2000", "name": "Liab", "type": "liability"},
    )
    lid = liab.json()["id"]
    r = await client.patch(
        f"/api/v1/accounts/{aid}",
        headers=_h(token),
        json={"parent_account_id": lid},
    )
    assert r.status_code == 400
    assert "type" in r.text.lower()
