"""YTD-by-vendor withholding report (Phase 9.7, #159)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import (
    auth_header,
    seed_full_ap_payments_stack,
    seed_issued_bill,
    seed_owner,
    seed_vendor,
    token_for,
)
from tests._withholding_helpers import (
    attach_profile_to_vendor,
    seed_withholding_liability_account,
    seed_withholding_profile,
)


@pytest.mark.asyncio
async def test_ytd_report_per_vendor(client: AsyncClient, app_session: AsyncSession) -> None:
    await seed_full_ap_payments_stack(app_session)
    user = await seed_owner(app_session, email="actor@example.com")
    vendor = await seed_vendor(app_session)
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="1000.00"
    )
    liability = await seed_withholding_liability_account(app_session)
    profile = await seed_withholding_profile(
        app_session, liability_account_id=liability.id, rate="0.10"
    )
    await attach_profile_to_vendor(app_session, vendor_id=vendor.id, profile_id=profile.id)

    owner = await token_for(Role.OWNER, client, app_session)
    body = {
        "vendor_id": str(vendor.id),
        "method": "ach",
        "amount": "1000.00",
        "applications": [{"bill_id": str(bill.id), "amount_applied": "1000.00"}],
    }
    r = await client.post("/api/v1/bill-payments", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text

    year = datetime.now(UTC).year
    resp = await client.get(
        f"/api/v1/withholding/ytd-by-vendor?year={year}",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["year"] == year
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["vendor_id"] == str(vendor.id)
    assert row["profile_code"] == "US-1099-NEC"
    assert row["form_kind"] == "1099-NEC"
    assert Decimal(row["total_paid"]) == Decimal("1000")
    assert Decimal(row["total_withheld"]) == Decimal("100")
    assert Decimal(payload["grand_total_paid"]) == Decimal("1000")
    assert Decimal(payload["grand_total_withheld"]) == Decimal("100")


@pytest.mark.asyncio
async def test_vendor_ytd_payments_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    await seed_full_ap_payments_stack(app_session)
    user = await seed_owner(app_session, email="actor@example.com")
    vendor = await seed_vendor(app_session)
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="500.00"
    )

    owner = await token_for(Role.OWNER, client, app_session)
    body = {
        "vendor_id": str(vendor.id),
        "method": "ach",
        "amount": "500.00",
        "applications": [{"bill_id": str(bill.id), "amount_applied": "500.00"}],
    }
    r = await client.post("/api/v1/bill-payments", headers=auth_header(owner), json=body)
    assert r.status_code == 201

    resp = await client.get(
        f"/api/v1/vendors/{vendor.id}/ytd-payments",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["total_paid"]) == Decimal("500")
