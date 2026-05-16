"""Partial application leaves bill in partially_paid; sum<amount stays pending (Phase 8.3, #130)."""

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
async def test_partial_apply_drops_bill_to_partially_paid(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Payment amount = application sum < bill outstanding → posts, bill partially_paid."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "check",
            "amount": "60.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "60.00"}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "posted"

    refreshed = (await app_session.execute(select(Bill).where(Bill.id == bill.id))).scalar_one()
    await app_session.refresh(refreshed)
    assert refreshed.amount_outstanding == Decimal("40.000000")
    assert refreshed.amount_paid == Decimal("60.000000")
    assert refreshed.state == BillState.PARTIALLY_PAID


@pytest.mark.asyncio
async def test_over_application_to_single_bill_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "check",
            "amount": "200.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "200.00"}],
        },
    )
    assert r.status_code == 400
    assert "outstanding" in r.json()["detail"].lower() or "exceeds" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_apply_sum_less_than_amount_stays_pending(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Sum(applications) < amount → don't auto-post; payment stays pending."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "wire",
            "amount": "100.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "60.00"}],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "pending"
    assert body["posting_journal_entry_id"] is None
