"""HTTP-driven bank import test (Phase 8.9, #136).

Exercises the full path: upload → run summary → transactions list.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    sample_csv_signed_amount,
    sample_ofx_bytes,
    seed_bank_account,
    token_for,
)


@pytest.mark.asyncio
async def test_csv_upload_with_mapping(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_bank_account(app_session)

    # Create a CSV mapping.
    r = await client.post(
        "/api/v1/bank-import-mappings",
        json={
            "name": "wells-signed",
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
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # Upload the file.
    upload = await client.post(
        "/api/v1/bank-imports",
        data={"account_id": str(acct.id), "mapping_id": mid},
        files={"file": ("april.csv", sample_csv_signed_amount(), "text/csv")},
        headers=auth_header(token),
    )
    assert upload.status_code == 201, upload.text
    run = upload.json()
    assert run["row_count"] == 4
    assert run["inserted_count"] == 4
    assert run["duplicate_count"] == 0
    run_id = run["id"]

    # Fetch the run summary.
    r2 = await client.get(f"/api/v1/bank-imports/{run_id}", headers=auth_header(token))
    assert r2.status_code == 200
    assert r2.json()["inserted_count"] == 4

    # List the transactions.
    r3 = await client.get(
        "/api/v1/bank-transactions",
        params={"account_id": str(acct.id)},
        headers=auth_header(token),
    )
    assert r3.status_code == 200
    body = r3.json()
    assert len(body["items"]) == 4
    descs = {i["description"] for i in body["items"]}
    assert "DEPOSIT PAYROLL" in descs


@pytest.mark.asyncio
async def test_ofx_upload_no_mapping(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_bank_account(app_session)

    upload = await client.post(
        "/api/v1/bank-imports",
        data={"account_id": str(acct.id)},
        files={
            "file": ("statement.ofx", sample_ofx_bytes(), "application/x-ofx"),
        },
        headers=auth_header(token),
    )
    assert upload.status_code == 201, upload.text
    run = upload.json()
    assert run["row_count"] == 2
    assert run["inserted_count"] == 2
    assert run["mapping_id"] is None
