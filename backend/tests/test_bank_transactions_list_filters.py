"""Bank transactions list-filter tests (Phase 8.9, #136).

Imports a small CSV, then asserts the GET /api/v1/bank-transactions
endpoint filters correctly on account / state / date_from / date_to /
search.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    sample_csv_signed_amount,
    seed_bank_account,
    token_for,
)


async def _seed_run(client: AsyncClient, token: str, app_session: AsyncSession) -> str:
    acct = await seed_bank_account(app_session)
    r = await client.post(
        "/api/v1/bank-import-mappings",
        json={
            "name": "m",
            "account_id": str(acct.id),
            "file_kind": "csv",
            "column_map": {
                "date": "Date",
                "description": "Description",
                "amount": "Amount",
                "balance": "Balance",
            },
            "date_format": "%Y-%m-%d",
            "amount_sign": "signed_amount",
        },
        headers=auth_header(token),
    )
    mid = r.json()["id"]
    await client.post(
        "/api/v1/bank-imports",
        data={"account_id": str(acct.id), "mapping_id": mid},
        files={"file": ("april.csv", sample_csv_signed_amount(), "text/csv")},
        headers=auth_header(token),
    )
    return str(acct.id)


@pytest.mark.asyncio
async def test_filter_by_account(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct_id = await _seed_run(client, token, app_session)
    r = await client.get(
        "/api/v1/bank-transactions",
        params={"account_id": acct_id},
        headers=auth_header(token),
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 4


@pytest.mark.asyncio
async def test_filter_by_date_range(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct_id = await _seed_run(client, token, app_session)
    # April 3 to 5 inclusive: COFFEE SHOP + DEPOSIT.
    r = await client.get(
        "/api/v1/bank-transactions",
        params={
            "account_id": acct_id,
            "date_from": "2026-04-03",
            "date_to": "2026-04-05",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 200
    descs = {i["description"] for i in r.json()["items"]}
    assert "COFFEE SHOP" in descs
    assert "DEPOSIT PAYROLL" in descs
    assert "RENT" not in descs


@pytest.mark.asyncio
async def test_filter_by_search(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct_id = await _seed_run(client, token, app_session)
    r = await client.get(
        "/api/v1/bank-transactions",
        params={"account_id": acct_id, "search": "payroll"},
        headers=auth_header(token),
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == "DEPOSIT PAYROLL"


@pytest.mark.asyncio
async def test_filter_by_state(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct_id = await _seed_run(client, token, app_session)
    # All freshly imported rows default to ``unmatched``.
    r = await client.get(
        "/api/v1/bank-transactions",
        params={"account_id": acct_id, "state": "unmatched"},
        headers=auth_header(token),
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 4

    r2 = await client.get(
        "/api/v1/bank-transactions",
        params={"account_id": acct_id, "state": "matched"},
        headers=auth_header(token),
    )
    assert r2.status_code == 200
    assert r2.json()["items"] == []
