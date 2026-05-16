"""One bill payment applied across multiple bills (Phase 8.3, #130)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.bill import Bill, BillState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import (
    auth_header,
    seed_full_ap_payments_stack,
    seed_issued_bill,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_one_payment_across_two_bills(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    b1 = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="60.00"
    )
    b2 = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="40.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "check",
            "amount": "100.00",
            "applications": [
                {"bill_id": str(b1.id), "amount_applied": "60.00"},
                {"bill_id": str(b2.id), "amount_applied": "40.00"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "posted"
    assert len(body["applications"]) == 2

    for bid in (b1.id, b2.id):
        refreshed = (await app_session.execute(select(Bill).where(Bill.id == bid))).scalar_one()
        await app_session.refresh(refreshed)
        assert refreshed.state == BillState.PAID
        assert refreshed.amount_outstanding == Decimal("0E-6")


@pytest.mark.asyncio
async def test_mixed_vendor_bills_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    """Applications must all target bills for the named vendor."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor_a = await seed_vendor(app_session, display_name="Vendor A")
    vendor_b = await seed_vendor(app_session, display_name="Vendor B")
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill_a = await seed_issued_bill(
        app_session, vendor=vendor_a, actor_user_id=user.id, unit_price="50.00"
    )
    bill_b = await seed_issued_bill(
        app_session, vendor=vendor_b, actor_user_id=user.id, unit_price="50.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor_a.id),
            "method": "ach",
            "amount": "100.00",
            "applications": [
                {"bill_id": str(bill_a.id), "amount_applied": "50.00"},
                {"bill_id": str(bill_b.id), "amount_applied": "50.00"},
            ],
        },
    )
    assert r.status_code == 400
    assert "different vendor" in r.json()["detail"]
