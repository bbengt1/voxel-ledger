"""Threshold-gating: large entries route to the approval queue (Phase 4.4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


async def _setup(client: AsyncClient, session: AsyncSession) -> tuple[str, str, str]:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    owner_token = await _login(client, "owner@example.com")
    cash = await client.post(
        "/api/v1/accounts",
        headers=_h(owner_token),
        json={"code": "1000", "name": "Cash", "type": "asset"},
    )
    rev = await client.post(
        "/api/v1/accounts",
        headers=_h(owner_token),
        json={"code": "4000", "name": "Revenue", "type": "revenue"},
    )
    return owner_token, cash.json()["id"], rev.json()["id"]


def _body(cash: str, rev: str, amount: str) -> dict:
    return {
        "description": "sale",
        "posted_at": datetime.now(UTC).isoformat(),
        "lines": [
            {"account_id": cash, "debit": amount, "credit": "0", "line_number": 1},
            {"account_id": rev, "debit": "0", "credit": amount, "line_number": 2},
        ],
    }


@pytest.mark.asyncio
async def test_under_threshold_posts_immediately(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner, cash, rev = await _setup(client, app_session)
    r = await client.post(
        "/api/v1/accounting/entries",
        headers=_h(owner),
        json=_body(cash, rev, "100.00"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "entry_number" in body
    assert body["entry_number"].startswith("JE-")


@pytest.mark.asyncio
async def test_above_threshold_routes_to_approval(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner, cash, rev = await _setup(client, app_session)
    # Default threshold is 1000.00.
    r = await client.post(
        "/api/v1/accounting/entries",
        headers=_h(owner),
        json=_body(cash, rev, "1500.00"),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending_approval"
    assert "approval_request_id" in body

    # The approval row exists.
    got = await client.get(
        f"/api/v1/approvals/{body['approval_request_id']}",
        headers=_h(owner),
    )
    assert got.status_code == 200
    ap = got.json()
    assert ap["state"] == "pending"
    assert ap["request_type"] == "accounting.large_journal_entry"
    assert ap["subject_kind"] == "journal_entry"
    assert ap["payload"]["description"] == "sale"
