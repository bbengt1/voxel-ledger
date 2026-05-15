"""Budget + division events surface in the audit log (Phase 4.5)."""

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
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_division_created_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    h = await _setup(client, app_session)
    create = await client.post(
        "/api/v1/accounting/divisions",
        headers=h,
        json={"name": "Consulting", "code": "CON"},
    )
    assert create.status_code == 201
    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.DivisionCreated"},
    )
    items = audit.json()["items"]
    assert items
    excerpt = items[0]["payload_excerpt"]
    assert excerpt["name"] == "Consulting"
    assert excerpt["code"] == "CON"


@pytest.mark.asyncio
async def test_budget_set_in_audit_log(client: AsyncClient, app_session: AsyncSession) -> None:
    h = await _setup(client, app_session)
    today = datetime.now(UTC).date()
    period = await client.post(
        "/api/v1/accounting/periods",
        headers=h,
        json={
            "name": "p",
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
        },
    )
    account = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "4000", "name": "Revenue", "type": "revenue"},
    )
    r = await client.post(
        "/api/v1/accounting/budgets",
        headers=h,
        json={
            "account_id": account.json()["id"],
            "period_id": period.json()["id"],
            "amount": "250.00",
        },
    )
    assert r.status_code == 200
    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.BudgetSet"},
    )
    items = audit.json()["items"]
    assert items
    excerpt = items[0]["payload_excerpt"]
    assert excerpt["new_amount"] == "250.000000"
    assert excerpt["old_amount"] is None
