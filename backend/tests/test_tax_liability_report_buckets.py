"""Tax-liability report aggregates per-rate collected / remitted / net (Phase 9.6, #158)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._tax_remittance_helpers import (
    auth_header,
    post_tax_collection,
    seed_tax_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_report_per_rate_buckets(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_tax_stack(app_session)  # 10% rate
    owner, user = await token_for(Role.OWNER, client, app_session)

    # Collect $25 in tax across two sales.
    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="100.00",
        tax="10.00",
        actor_user_id=user.id,
    )
    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="150.00",
        tax="15.00",
        actor_user_id=user.id,
    )

    today = datetime.now(UTC).date()
    # Remit $20 of the $25 collected.
    create_body = {
        "profile_id": str(accounts["profile_id"]),
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "amount_paid": "20.00",
        "paid_on": today.isoformat(),
        "method": "ach",
        "bank_account_id": str(accounts["bank_account_id"]),
        "allow_partial": True,
    }
    r = await client.post("/api/v1/tax-remittances", headers=auth_header(owner), json=create_body)
    assert r.status_code == 201, r.text

    date_from = (today - timedelta(days=30)).isoformat()
    date_to = today.isoformat()
    report_resp = await client.get(
        f"/api/v1/reports/tax-liability?date_from={date_from}&date_to={date_to}",
        headers=auth_header(owner),
    )
    assert report_resp.status_code == 200, report_resp.text
    body = report_resp.json()
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["rate_name"] == "State Sales Tax"
    assert row["jurisdiction"] == "US-CA"
    assert Decimal(row["tax_collected"]) == Decimal("25.00")
    assert Decimal(row["tax_remitted"]) == Decimal("20.00")
    assert Decimal(row["net_liability"]) == Decimal("5.00")
    # gross = collected / rate = 25 / 0.10 = 250
    assert Decimal(row["gross_taxable_sales"]) == Decimal("250.00")

    assert Decimal(body["grand_total_collected"]) == Decimal("25.00")
    assert Decimal(body["grand_total_remitted"]) == Decimal("20.00")
    assert Decimal(body["grand_total_net"]) == Decimal("5.00")
