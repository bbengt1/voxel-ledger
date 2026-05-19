"""Bill payment Cr-side splits when the vendor has a withholding profile (Phase 9.7, #159)."""

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
async def test_payment_with_vendor_profile_splits_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_full_ap_payments_stack(app_session)
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

    owner_token = await token_for(Role.OWNER, client, app_session)
    body = {
        "vendor_id": str(vendor.id),
        "method": "ach",
        "amount": "1000.00",
        "applications": [{"bill_id": str(bill.id), "amount_applied": "1000.00"}],
    }
    r = await client.post("/api/v1/bill-payments", headers=auth_header(owner_token), json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["state"] == "posted"
    app_row = payload["applications"][0]
    assert Decimal(app_row["withholding_amount"]) == Decimal("100")
    assert app_row["withholding_profile_id"] == str(profile.id)

    je_id = uuid.UUID(payload["posting_journal_entry_id"])
    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    by_account = {line.account_id: line for line in je.lines}
    # Dr AP $1000
    assert by_account[accounts["ap_account_id"]].debit == Decimal("1000.000000")
    # Cr Bank $900, Cr Withholding-Liability $100
    assert by_account[accounts["bank_account_id"]].credit == Decimal("900.000000")
    assert by_account[liability.id].credit == Decimal("100.000000")

    total_d = sum(line.debit for line in je.lines)
    total_c = sum(line.credit for line in je.lines)
    assert total_d == total_c == Decimal("1000.000000")
