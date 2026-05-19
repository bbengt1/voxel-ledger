"""Threshold gate: YTD < threshold suppresses withholding (Phase 9.7, #159)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.journal_entry import JournalEntry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
async def test_below_threshold_no_split(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_full_ap_payments_stack(app_session)
    user = await seed_owner(app_session, email="actor@example.com")
    vendor = await seed_vendor(app_session)
    # First-ever payment for this vendor; YTD-before == 0 < $600 threshold.
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="400.00"
    )
    liability = await seed_withholding_liability_account(app_session)
    profile = await seed_withholding_profile(
        app_session,
        liability_account_id=liability.id,
        rate="0.10",
        threshold_per_year="600.00",
    )
    await attach_profile_to_vendor(app_session, vendor_id=vendor.id, profile_id=profile.id)

    owner = await token_for(Role.OWNER, client, app_session)
    body = {
        "vendor_id": str(vendor.id),
        "method": "ach",
        "amount": "400.00",
        "applications": [{"bill_id": str(bill.id), "amount_applied": "400.00"}],
    }
    r = await client.post("/api/v1/bill-payments", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    app_row = r.json()["applications"][0]
    assert Decimal(app_row["withholding_amount"]) == Decimal("0")
    assert app_row["withholding_profile_id"] is None

    # JE: Dr AP $400 / Cr Bank $400 (no withholding line).
    je_id = uuid.UUID(r.json()["posting_journal_entry_id"])
    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    by_account = {line.account_id: line for line in je.lines}
    assert by_account[accounts["bank_account_id"]].credit == Decimal("400.000000")
    assert liability.id not in by_account
