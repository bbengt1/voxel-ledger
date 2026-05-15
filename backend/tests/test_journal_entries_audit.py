"""Journal-entry events surface in the audit log (Phase 4.2).

The Posted excerpt summarizes lines (count + totals) rather than
embedding the full lines array.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    # Phase 4.3: posts require a covering open period.
    await client.post(
        "/api/v1/accounting/periods",
        headers=headers,
        json={
            "name": "test-current",
            "start_date": "2000-01-01",
            "end_date": "2100-12-31",
        },
    )
    return headers


@pytest.mark.asyncio
async def test_posted_event_in_audit_log_with_lines_summary(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    h = await _setup(client, app_session)
    cash = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "1000", "name": "Cash", "type": "asset"},
    )
    rev = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "4000", "name": "Revenue", "type": "revenue"},
    )
    await client.post(
        "/api/v1/accounting/entries",
        headers=h,
        json={
            "description": "audit sale",
            "posted_at": datetime.now(UTC).isoformat(),
            "lines": [
                {
                    "account_id": cash.json()["id"],
                    "debit": "50",
                    "credit": "0",
                    "line_number": 1,
                },
                {
                    "account_id": rev.json()["id"],
                    "debit": "0",
                    "credit": "50",
                    "line_number": 2,
                },
            ],
        },
    )

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.JournalEntryPosted"},
    )
    body = audit.json()
    assert body["items"]
    row = body["items"][0]
    excerpt = row["payload_excerpt"]
    assert excerpt["description"] == "audit sale"
    assert excerpt["entry_number"].startswith("JE-")
    # Lines summary only — no raw lines list.
    summary = excerpt["lines"]
    assert summary["count"] == 2
    from decimal import Decimal

    assert Decimal(summary["total_debit"]) == Decimal("50")
    assert Decimal(summary["total_credit"]) == Decimal("50")
    assert "account_id" not in str(summary)


@pytest.mark.asyncio
async def test_reversed_event_in_audit_log(client: AsyncClient, app_session: AsyncSession) -> None:
    h = await _setup(client, app_session)
    cash = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "1000", "name": "Cash", "type": "asset"},
    )
    rev = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "4000", "name": "Revenue", "type": "revenue"},
    )
    entry = await client.post(
        "/api/v1/accounting/entries",
        headers=h,
        json={
            "description": "to be reversed",
            "posted_at": datetime.now(UTC).isoformat(),
            "lines": [
                {
                    "account_id": cash.json()["id"],
                    "debit": "10",
                    "credit": "0",
                    "line_number": 1,
                },
                {
                    "account_id": rev.json()["id"],
                    "debit": "0",
                    "credit": "10",
                    "line_number": 2,
                },
            ],
        },
    )
    await client.post(
        f"/api/v1/accounting/entries/{entry.json()['id']}/reverse",
        headers=h,
        json={},
    )
    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.JournalEntryReversed"},
    )
    items = audit.json()["items"]
    assert items
    excerpt = items[0]["payload_excerpt"]
    assert excerpt["original_entry_id"] == entry.json()["id"]
    assert excerpt["reversal_entry_number"].startswith("JE-")
