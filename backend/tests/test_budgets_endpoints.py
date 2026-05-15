"""Budgets API: role matrix (Phase 4.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_slot(client: AsyncClient, owner_token: str) -> dict[str, str]:
    """Set up an account + period; return their IDs."""
    today = datetime.now(UTC).date()
    period = await client.post(
        "/api/v1/accounting/periods",
        headers=_h(owner_token),
        json={
            "name": "test-period",
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
        },
    )
    account = await client.post(
        "/api/v1/accounts",
        headers=_h(owner_token),
        json={"code": "4000", "name": "Revenue", "type": "revenue"},
    )
    return {
        "period_id": period.json()["id"],
        "account_id": account.json()["id"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_upsert_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    slot = await _seed_slot(client, owner)
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/accounting/budgets",
        headers=_h(token),
        json={
            "account_id": slot["account_id"],
            "period_id": slot["period_id"],
            "amount": "1000.00",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_visible_to_owner_and_bookkeeper(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    bk_token = await _token_for(Role.BOOKKEEPER, client, app_session)
    r = await client.get("/api/v1/accounting/budgets", headers=_h(bk_token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/accounting/budgets")
    assert r.status_code == 401
