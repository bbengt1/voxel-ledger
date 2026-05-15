"""GET /accounting/account-balances respects each type's natural sign (Phase 4.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
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
async def test_natural_sign_per_type(client: AsyncClient, app_session: AsyncSession) -> None:
    h = await _owner(client, app_session)

    # Asset, expense (debit-normal); liability, equity, revenue (credit-normal).
    accounts = {}
    for code, typ in [
        ("1000", "asset"),
        ("2000", "liability"),
        ("3000", "equity"),
        ("4000", "revenue"),
        ("5000", "expense"),
    ]:
        r = await client.post(
            "/api/v1/accounts",
            headers=h,
            json={"code": code, "name": f"{typ} acct", "type": typ},
        )
        accounts[typ] = r.json()["id"]

    # Post: A debit 60, expense 40, liability credit 30, equity credit 20, revenue 50.
    await client.post(
        "/api/v1/accounting/entries",
        headers=h,
        json={
            "description": "mixed",
            "posted_at": datetime.now(UTC).isoformat(),
            "lines": [
                {
                    "account_id": accounts["asset"],
                    "debit": "60",
                    "credit": "0",
                    "line_number": 1,
                },
                {
                    "account_id": accounts["expense"],
                    "debit": "40",
                    "credit": "0",
                    "line_number": 2,
                },
                {
                    "account_id": accounts["liability"],
                    "debit": "0",
                    "credit": "30",
                    "line_number": 3,
                },
                {
                    "account_id": accounts["equity"],
                    "debit": "0",
                    "credit": "20",
                    "line_number": 4,
                },
                {
                    "account_id": accounts["revenue"],
                    "debit": "0",
                    "credit": "50",
                    "line_number": 5,
                },
            ],
        },
    )

    r = await client.get("/api/v1/accounting/account-balances", headers=h)
    items = {it["account_id"]: it for it in r.json()["items"]}
    # Debit-normal: balance = debits - credits = positive.
    assert Decimal(items[accounts["asset"]]["balance"]) == Decimal("60")
    assert Decimal(items[accounts["expense"]]["balance"]) == Decimal("40")
    # Credit-normal: balance = credits - debits.
    assert Decimal(items[accounts["liability"]]["balance"]) == Decimal("30")
    assert Decimal(items[accounts["equity"]]["balance"]) == Decimal("20")
    assert Decimal(items[accounts["revenue"]]["balance"]) == Decimal("50")


@pytest.mark.asyncio
async def test_account_with_no_activity_returns_zero(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    h = await _owner(client, app_session)
    cash = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "1000", "name": "Cash", "type": "asset"},
    )
    r = await client.get(
        "/api/v1/accounting/account-balances",
        headers=h,
        params={"account_id": cash.json()["id"]},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert Decimal(items[0]["total_debits"]) == Decimal("0")
    assert Decimal(items[0]["total_credits"]) == Decimal("0")
    assert Decimal(items[0]["balance"]) == Decimal("0")
