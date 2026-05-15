"""DELETE /api/v1/accounting/budgets behavior (Phase 4.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _setup(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    token = login.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    today = datetime.now(UTC).date()
    period = await client.post(
        "/api/v1/accounting/periods",
        headers=h,
        json={
            "name": "test-period",
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
        },
    )
    account = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "5000", "name": "COGS", "type": "expense"},
    )
    return {
        "h": h,
        "period_id": period.json()["id"],
        "account_id": account.json()["id"],
    }


@pytest.mark.asyncio
async def test_delete_existing_204(client: AsyncClient, app_session: AsyncSession) -> None:
    ctx = await _setup(client, app_session)
    await client.post(
        "/api/v1/accounting/budgets",
        headers=ctx["h"],
        json={
            "account_id": ctx["account_id"],
            "period_id": ctx["period_id"],
            "amount": "500.00",
        },
    )
    r = await client.request(
        "DELETE",
        "/api/v1/accounting/budgets",
        headers=ctx["h"],
        json={
            "account_id": ctx["account_id"],
            "period_id": ctx["period_id"],
        },
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_nonexistent_404(client: AsyncClient, app_session: AsyncSession) -> None:
    ctx = await _setup(client, app_session)
    r = await client.request(
        "DELETE",
        "/api/v1/accounting/budgets",
        headers=ctx["h"],
        json={
            "account_id": ctx["account_id"],
            "period_id": ctx["period_id"],
        },
    )
    assert r.status_code == 404
