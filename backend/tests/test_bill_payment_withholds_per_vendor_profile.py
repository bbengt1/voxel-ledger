"""Bill payment splits withholding when the vendor has a profile (Phase 9.7, #159).

QBO is the sole ledger (epic #312, Phase 5e): the withholding split rides
the sync outbox as a ``bill_payment_withholding`` JournalEntry spec
alongside the native ``bill_payment`` document.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.qbo_sync_outbox import QboSyncOutbox
from httpx import AsyncClient
from sqlalchemy import select
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
async def test_payment_with_vendor_profile_splits_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
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
    # QBO is the sole ledger: no local JE.
    assert payload["posting_journal_entry_id"] is None

    # Outbox carries the native BillPayment + the withholding split JE spec.
    rows = (
        (
            await app_session.execute(
                select(QboSyncOutbox).where(
                    QboSyncOutbox.local_id == uuid.UUID(payload["id"]),
                )
            )
        )
        .scalars()
        .all()
    )
    by_kind = {row.kind: row for row in rows}
    assert set(by_kind) == {"bill_payment", "bill_payment_withholding"}
    assert by_kind["bill_payment"].op == "post"

    withholding_lines = by_kind["bill_payment_withholding"].payload["lines"]
    by_role = {line["role"]: line for line in withholding_lines}
    assert by_role["bank"]["posting"] == "debit"
    assert Decimal(by_role["bank"]["amount"]) == Decimal("100")
    assert by_role["tax_liability"]["posting"] == "credit"
    assert Decimal(by_role["tax_liability"]["amount"]) == Decimal("100")
