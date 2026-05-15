"""Accounting-period events surface in the audit log (Phase 4.3, #66)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_close_lock_appear_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    h = await _owner_headers(client, app_session)
    created = await client.post(
        "/api/v1/accounting/periods",
        headers=h,
        json={"name": "2026-Q1", "start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    pid = created.json()["id"]
    await client.post(f"/api/v1/accounting/periods/{pid}/close", headers=h)
    await client.post(f"/api/v1/accounting/periods/{pid}/lock", headers=h)

    for et in (
        "accounting.PeriodCreated",
        "accounting.PeriodClosed",
        "accounting.PeriodLocked",
    ):
        r = await client.get("/api/v1/admin/audit-log", headers=h, params={"event_type": et})
        body = r.json()
        assert body["items"], f"no audit row for {et}"
        row = body["items"][0]
        assert row["summary"], f"empty summary for {et}"
