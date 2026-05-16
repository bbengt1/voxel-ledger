"""Unapply / bounce / cancel reverse the JE and restore bill state (Phase 8.3, #130)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.bill import Bill, BillState
from app.models.bill_payment import BillPayment, BillPaymentState
from app.models.journal_line import JournalLine
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
async def test_unapply_reverses_je_and_restores_bill_outstanding(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    bookkeeper = await token_for(Role.BOOKKEEPER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "bookkeeper@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="200.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(bookkeeper),
        json={
            "vendor_id": str(vendor.id),
            "method": "wire",
            "amount": "200.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "200.00"}],
        },
    )
    assert r.status_code == 201
    payment_id = r.json()["id"]

    # Pre-snapshot balanced books
    pre_d = sum(
        (await app_session.execute(select(JournalLine.debit))).scalars().all(),
        Decimal("0"),
    )
    pre_c = sum(
        (await app_session.execute(select(JournalLine.credit))).scalars().all(),
        Decimal("0"),
    )
    assert pre_d == pre_c

    r = await client.post(
        f"/api/v1/bill-payments/{payment_id}/unapply", headers=auth_header(bookkeeper)
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "pending"
    assert r.json()["applications"] == []

    # Bill restored
    refreshed = (await app_session.execute(select(Bill).where(Bill.id == bill.id))).scalar_one()
    await app_session.refresh(refreshed)
    assert refreshed.amount_paid == Decimal("0E-6")
    assert refreshed.amount_outstanding == Decimal("200.000000")
    assert refreshed.state == BillState.ISSUED

    # Books still balanced
    post_d = sum(
        (await app_session.execute(select(JournalLine.debit))).scalars().all(),
        Decimal("0"),
    )
    post_c = sum(
        (await app_session.execute(select(JournalLine.credit))).scalars().all(),
        Decimal("0"),
    )
    assert post_d == post_c

    payment = (
        await app_session.execute(
            select(BillPayment).where(BillPayment.id == uuid.UUID(payment_id))
        )
    ).scalar_one()
    await app_session.refresh(payment)
    assert payment.state == BillPaymentState.PENDING
    assert payment.posting_journal_entry_id is None


@pytest.mark.asyncio
async def test_bounce_from_posted_flips_state(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    bookkeeper = await token_for(Role.BOOKKEEPER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "bookkeeper@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="50.00"
    )

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(bookkeeper),
        json={
            "vendor_id": str(vendor.id),
            "method": "check",
            "amount": "50.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "50.00"}],
        },
    )
    payment_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/bill-payments/{payment_id}/bounce", headers=auth_header(bookkeeper)
    )
    assert r.status_code == 200
    assert r.json()["state"] == "bounced"


@pytest.mark.asyncio
async def test_cancel_pending_payment(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "cash",
            "amount": "25.00",
        },
    )
    assert r.status_code == 201
    assert r.json()["state"] == "pending"
    payment_id = r.json()["id"]

    r = await client.post(f"/api/v1/bill-payments/{payment_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_posted_payment_reverses_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="50.00"
    )
    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "ach",
            "amount": "50.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "50.00"}],
        },
    )
    assert r.status_code == 201
    payment_id = r.json()["id"]

    r = await client.post(f"/api/v1/bill-payments/{payment_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"

    refreshed = (await app_session.execute(select(Bill).where(Bill.id == bill.id))).scalar_one()
    await app_session.refresh(refreshed)
    assert refreshed.state == BillState.ISSUED
    assert refreshed.amount_outstanding == Decimal("50.000000")
