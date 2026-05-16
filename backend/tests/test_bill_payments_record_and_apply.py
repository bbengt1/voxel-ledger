"""One-shot bill payment posts Dr AP / Cr Bank, drives bill to paid (Phase 8.3, #130)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.bill import Bill, BillState
from app.models.bill_payment import BillPayment, BillPaymentState
from app.models.journal_entry import JournalEntry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._bill_payments_helpers import (
    auth_header,
    seed_full_ap_payments_stack,
    seed_issued_bill,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_record_payment_full_amount_drives_bill_paid(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )
    assert bill.amount_outstanding == Decimal("100.000000")

    body = {
        "vendor_id": str(vendor.id),
        "method": "ach",
        "amount": "100.00",
        "applications": [{"bill_id": str(bill.id), "amount_applied": "100.00"}],
    }
    r = await client.post("/api/v1/bill-payments", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payment_body = r.json()
    assert payment_body["state"] == "posted"
    assert payment_body["payment_number"].startswith("BP-")
    assert payment_body["posting_journal_entry_id"] is not None
    assert len(payment_body["applications"]) == 1

    # Bill paid
    refreshed = (await app_session.execute(select(Bill).where(Bill.id == bill.id))).scalar_one()
    await app_session.refresh(refreshed)
    assert refreshed.amount_paid == Decimal("100.000000")
    assert refreshed.amount_outstanding == Decimal("0E-6")
    assert refreshed.state == BillState.PAID

    # JE has AP debit + Bank credit
    je_id = uuid.UUID(payment_body["posting_journal_entry_id"])
    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    by_acct = {line.account_id: line for line in je.lines}
    assert by_acct[accounts["ap_account_id"]].debit == Decimal("100.000000")
    assert by_acct[accounts["bank_account_id"]].credit == Decimal("100.000000")

    # Payment state in DB
    payment = (
        await app_session.execute(
            select(BillPayment).where(BillPayment.id == uuid.UUID(payment_body["id"]))
        )
    ).scalar_one()
    await app_session.refresh(payment)
    assert payment.state == BillPaymentState.POSTED


@pytest.mark.asyncio
async def test_record_payment_zero_amount_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={"vendor_id": str(vendor.id), "method": "ach", "amount": "0"},
    )
    assert r.status_code == 400
