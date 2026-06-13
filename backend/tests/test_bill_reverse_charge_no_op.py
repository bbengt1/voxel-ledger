"""Bills: reverse-charge profile zeroes line.tax_amount (9.5).

QBO is the sole ledger (epic #312, Phase 5e): the issue enqueues a QBO
Bill outbox row whose spec must carry zero tax for reverse-charge lines.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.bill import BillItem
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.models.vendor import Vendor
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import (
    auth_header,
    sample_bill_body,
    seed_full_ap_stack,
    seed_vendor,
    token_for,
)
from tests._tax_helpers import seed_liability_account, seed_tax_profile


@pytest.mark.asyncio
async def test_bill_reverse_charge_line_zero_no_je_tax(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_stack(app_session, with_tax=True)
    liability_acct = await seed_liability_account(app_session)
    await app_session.commit()
    profile = await seed_tax_profile(
        app_session,
        code="EU-BILL-RC",
        name="EU Bill RC",
        jurisdiction="EU",
        is_reverse_charge=True,
        rates=[("VAT", Decimal("0.20"), liability_acct.id, False)],
    )
    vendor = await seed_vendor(app_session)
    vendor_row = (
        await app_session.execute(select(Vendor).where(Vendor.id == vendor.id))
    ).scalar_one()
    vendor_row.tax_profile_id = profile.id
    await app_session.commit()

    # Bill with no flat tax — narrow-scope contract: tax_amount stays 0
    # at draft, no JE distortion at issue.
    body = sample_bill_body(
        vendor_id=str(vendor.id),
        items=[
            {
                "kind": "manual",
                "description": "Service",
                "quantity": "1",
                "unit_price": "100.00",
            }
        ],
    )
    create = await client.post("/api/v1/bills", headers=auth_header(owner), json=body)
    assert create.status_code == 201, create.text
    bill_id = create.json()["id"]

    issued = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    # QBO is the sole ledger: no local JE.
    assert issued.json()["posting_journal_entry_id"] is None

    # The QBO outbox spec carries zero tax (reverse-charge is memo-only).
    outbox = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "bill",
                QboSyncOutbox.local_id == uuid.UUID(bill_id),
            )
        )
    ).scalar_one()
    assert Decimal(outbox.payload["tax_amount"]) == Decimal("0")
    # Bill item line.tax_amount stored as zero
    items = list(
        (await app_session.execute(select(BillItem).where(BillItem.bill_id == uuid.UUID(bill_id))))
        .scalars()
        .all()
    )
    assert all(item.tax_amount == Decimal("0") for item in items)
