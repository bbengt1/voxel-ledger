"""Journal-entries API: role matrix + happy path (Phase 4.2)."""

from __future__ import annotations

from datetime import UTC, datetime

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


async def _seed_accounts(client: AsyncClient, owner_token: str) -> tuple[str, str]:
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
    await _seed_open_period(client, owner_token)
    return cash.json()["id"], rev.json()["id"]


async def _seed_open_period(client: AsyncClient, owner_token: str) -> None:
    """Phase 4.3: posts require a covering open period.

    Idempotent — if a 400 (overlap) comes back, an earlier test already
    seeded one.
    """
    await client.post(
        "/api/v1/accounting/periods",
        headers=_h(owner_token),
        json={"name": "test-current", "start_date": "2000-01-01", "end_date": "2100-12-31"},
    )


def _entry_body(cash_id: str, rev_id: str) -> dict:
    return {
        "description": "sale",
        "posted_at": datetime.now(UTC).isoformat(),
        "lines": [
            {
                "account_id": cash_id,
                "debit": "100",
                "credit": "0",
                "line_number": 1,
            },
            {
                "account_id": rev_id,
                "debit": "0",
                "credit": "100",
                "line_number": 2,
            },
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 201),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_post_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner_token = await _token_for(Role.OWNER, client, app_session)
    cash_id, rev_id = await _seed_accounts(client, owner_token)
    token = owner_token if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/accounting/entries",
        headers=_h(token),
        json=_entry_body(cash_id, rev_id),
    )
    assert r.status_code == expected, r.text


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
async def test_list_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/accounting/entries", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_post_get_list_reverse_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    cash_id, rev_id = await _seed_accounts(client, owner)

    posted = await client.post(
        "/api/v1/accounting/entries",
        headers=_h(owner),
        json=_entry_body(cash_id, rev_id),
    )
    assert posted.status_code == 201, posted.text
    body = posted.json()
    eid = body["id"]
    assert body["entry_number"].startswith("JE-")
    assert body["is_reversed"] is False
    assert len(body["lines"]) == 2
    assert body["lines"][0]["account_code"] in ("1000", "4000")

    got = await client.get(f"/api/v1/accounting/entries/{eid}", headers=_h(owner))
    assert got.status_code == 200

    listed = await client.get("/api/v1/accounting/entries", headers=_h(owner))
    assert listed.status_code == 200
    assert any(item["id"] == eid for item in listed.json()["items"])

    rev = await client.post(
        f"/api/v1/accounting/entries/{eid}/reverse",
        headers=_h(owner),
        json={},
    )
    assert rev.status_code == 201, rev.text
    assert rev.json()["reversal_of_entry_id"] == eid


@pytest.mark.asyncio
async def test_balances_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    cash_id, rev_id = await _seed_accounts(client, owner)
    await client.post(
        "/api/v1/accounting/entries",
        headers=_h(owner),
        json=_entry_body(cash_id, rev_id),
    )

    r = await client.get("/api/v1/accounting/account-balances", headers=_h(owner))
    assert r.status_code == 200, r.text
    from decimal import Decimal

    items = {it["account_id"]: it for it in r.json()["items"]}
    # Cash is asset (debit-normal) → balance = 100 - 0 = 100
    assert Decimal(items[cash_id]["balance"]) == Decimal("100")
    # Revenue is credit-normal → balance = 100 - 0 = 100
    assert Decimal(items[rev_id]["balance"]) == Decimal("100")


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/accounting/entries" in paths
    assert "/api/v1/accounting/entries/{entry_id}" in paths
    assert "/api/v1/accounting/entries/{entry_id}/reverse" in paths
    assert "/api/v1/accounting/account-balances" in paths
