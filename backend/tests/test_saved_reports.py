"""Saved reports tests (Parity #237)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.saved_report import SavedReport
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(client: AsyncClient, session: AsyncSession, *, email: str, role: Role) -> str:
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=email,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_create_list_roundtrip_filters_intact(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(client, app_session, email="sr-rt@example.com", role=Role.BOOKKEEPER)
    hdrs = {"Authorization": f"Bearer {token}"}

    filters = {
        "date_from": "2026-05-01",
        "date_to": "2026-05-31",
        "division_id": None,
        "nested": {"a": 1, "b": [1, 2, 3]},
    }
    create = await client.post(
        "/api/v1/saved-reports",
        headers=hdrs,
        json={
            "name": "May P&L",
            "report_kind": "income_statement",
            "filters": filters,
        },
    )
    assert create.status_code == 201, create.text
    saved_id = create.json()["id"]
    # Filters round-trip without loss (including nested + None).
    assert create.json()["filters"] == filters

    listed = await client.get(
        "/api/v1/saved-reports",
        headers=hdrs,
        params={"report_kind": "income_statement"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["id"] == saved_id
    assert body[0]["filters"] == filters


@pytest.mark.asyncio
async def test_per_user_isolation(client: AsyncClient, app_session: AsyncSession) -> None:
    """User A cannot see, read, or delete User B's saved reports."""
    token_a = await _token(client, app_session, email="a@example.com", role=Role.BOOKKEEPER)
    token_b = await _token(client, app_session, email="b@example.com", role=Role.BOOKKEEPER)

    create_a = await client.post(
        "/api/v1/saved-reports",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Mine", "report_kind": "trial_balance", "filters": {}},
    )
    assert create_a.status_code == 201
    a_id = create_a.json()["id"]

    # User B's list is empty.
    list_b = await client.get(
        "/api/v1/saved-reports",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_b.status_code == 200
    assert list_b.json() == []

    # User B's get → 404.
    get_b = await client.get(
        f"/api/v1/saved-reports/{a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_b.status_code == 404

    # User B's delete → 404.
    delete_b = await client.delete(
        f"/api/v1/saved-reports/{a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert delete_b.status_code == 404

    # A's row still alive.
    rows = (await app_session.execute(select(SavedReport))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_duplicate_name_per_kind_rejected_per_user(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(client, app_session, email="dup@example.com", role=Role.BOOKKEEPER)
    hdrs = {"Authorization": f"Bearer {token}"}
    body = {"name": "Same", "report_kind": "income_statement", "filters": {}}
    first = await client.post("/api/v1/saved-reports", headers=hdrs, json=body)
    assert first.status_code == 201

    dup = await client.post("/api/v1/saved-reports", headers=hdrs, json=body)
    assert dup.status_code == 409

    # Same name under a DIFFERENT kind is fine.
    other_kind = await client.post(
        "/api/v1/saved-reports",
        headers=hdrs,
        json={"name": "Same", "report_kind": "balance_sheet", "filters": {}},
    )
    assert other_kind.status_code == 201


@pytest.mark.asyncio
async def test_update_and_delete(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token(client, app_session, email="upd@example.com", role=Role.BOOKKEEPER)
    hdrs = {"Authorization": f"Bearer {token}"}
    create = await client.post(
        "/api/v1/saved-reports",
        headers=hdrs,
        json={"name": "Old", "report_kind": "income_statement", "filters": {"a": 1}},
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    patch = await client.patch(
        f"/api/v1/saved-reports/{sid}",
        headers=hdrs,
        json={"name": "New", "filters": {"b": 2}},
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "New"
    assert patch.json()["filters"] == {"b": 2}

    delete = await client.delete(f"/api/v1/saved-reports/{sid}", headers=hdrs)
    assert delete.status_code == 204

    after = await client.get("/api/v1/saved-reports", headers=hdrs)
    assert after.json() == []
