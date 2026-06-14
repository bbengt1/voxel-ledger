"""Bill issue handles expense_category lines (Phase 8.6, #133).

QBO replace-mode (epic #312, Phase 5e): bill issue no longer posts a local JE,
so the old per-category GL-account routing is gone — a native QBO Bill maps
every expense line to the role-mapped "expense" account (see
``builders._create_bill``). This test now verifies the operational invariant
that still matters: an ``expense_category`` line (alongside a ``manual`` line)
flows through issue, leaves ``posting_journal_entry_id`` None, and enqueues a
``bill`` sync-outbox row carrying the correct per-line amounts.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.account import Account
from app.models.auth import Role
from app.models.qbo_sync_outbox import QboSyncOutbox
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


@pytest.mark.asyncio
async def test_category_line_enqueues_bill_with_line_amounts(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_stack(app_session, with_tax=False)
    vendor = await seed_vendor(app_session)

    # The category still requires a default_expense_account_id (API contract),
    # but that routing account is no longer used by the QBO push — every expense
    # line maps to the role-mapped "expense" account at drain.
    cat_acct = Account(id=uuid.uuid4(), code="5500", name="Travel Expense", type="expense")
    app_session.add(cat_acct)
    await app_session.commit()

    cat_r = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "TRAVEL",
            "name": "Travel",
            "default_expense_account_id": str(cat_acct.id),
        },
        headers=auth_header(owner),
    )
    assert cat_r.status_code == 201, cat_r.text
    category_id = cat_r.json()["id"]

    body = sample_bill_body(
        vendor_id=str(vendor.id),
        items=[
            {
                "kind": "expense_category",
                "expense_category_id": category_id,
                "description": "Flight",
                "quantity": "1",
                "unit_price": "120.00",
            },
            {
                "kind": "manual",
                "description": "Office",
                "quantity": "1",
                "unit_price": "30.00",
            },
        ],
    )
    create = await client.post("/api/v1/bills", headers=auth_header(owner), json=body)
    assert create.status_code == 201, create.text
    bill_id = create.json()["id"]

    issued = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    # QBO is the sole ledger now — no local JE.
    assert issued.json()["posting_journal_entry_id"] is None

    row = (
        await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "bill"))
    ).scalar_one()
    assert str(row.local_id) == bill_id
    amounts = sorted(Decimal(line["amount"]) for line in row.payload["lines"])
    assert amounts == [Decimal("30.00"), Decimal("120.00")]
