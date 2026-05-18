"""Bill issue uses expense_category default expense account (Phase 8.6, #133)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.account import Account
from app.models.auth import Role
from app.models.journal_entry import JournalEntry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._bills_helpers import (
    auth_header,
    sample_bill_body,
    seed_full_ap_stack,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_category_default_account_used_for_line(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    base = await seed_full_ap_stack(app_session, with_tax=False)
    vendor = await seed_vendor(app_session)

    # A second expense account that belongs to the category.
    cat_acct = Account(id=uuid.uuid4(), code="5500", name="Travel Expense", type="expense")
    app_session.add(cat_acct)
    await app_session.commit()

    # Create the category via the API.
    cat_r = await client.post(
        "/api/v1/expense-categories",
        json={
            "code": "TRAVEL",
            "name": "Travel",
            "default_expense_account_id": str(cat_acct.id),
        },
        headers=auth_header(owner),
    )
    assert cat_r.status_code == 201
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
    je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])

    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == je_id)
        .options(selectinload(JournalEntry.lines))
    )
    je = (await app_session.execute(stmt)).scalar_one()
    debits_by_account: dict[uuid.UUID, Decimal] = {}
    for line in je.lines:
        if line.debit > 0:
            debits_by_account[line.account_id] = (
                debits_by_account.get(line.account_id, Decimal("0")) + line.debit
            )

    assert debits_by_account.get(cat_acct.id) == Decimal("120.000000")
    # The other line had no category; falls back to the AP-stack default
    # expense account (the setting fallback, since the seeded vendor has
    # no default_expense_account_id).
    assert debits_by_account.get(base["expense_account_id"]) == Decimal("30.000000")
