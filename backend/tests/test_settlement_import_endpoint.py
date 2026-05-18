"""Multipart settlement import endpoint smoke test (Phase 9.8, #160)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import (
    auth_header,
    sample_etsy_csv_bytes,
    seed_settlement_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_import_endpoint_creates_settlement_with_lines(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    stack = await seed_settlement_stack(app_session)
    token = await token_for(Role.OWNER, client, app_session)

    csv_bytes = sample_etsy_csv_bytes()
    r = await client.post(
        "/api/v1/settlements",
        headers=auth_header(token),
        data={
            "channel_id": str(stack["channel_id"]),
            "format_kind": "etsy",
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
            "payout_account_id": str(stack["payout_account_id"]),
        },
        files={"file": ("etsy.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["settlement_number"].startswith("SETT-")
    settlement_id = body["id"]
    assert body["state"] == "imported"

    # GET returns settlement + lines together.
    r2 = await client.get(f"/api/v1/settlements/{settlement_id}", headers=auth_header(token))
    assert r2.status_code == 200, r2.text
    detail = r2.json()
    assert len(detail["lines"]) == 5
    assert detail["settlement"]["settlement_number"] == body["settlement_number"]

    # List endpoint surfaces the new row.
    r3 = await client.get("/api/v1/settlements", headers=auth_header(token))
    assert r3.status_code == 200
    listed = r3.json()
    assert any(item["id"] == settlement_id for item in listed["items"])
