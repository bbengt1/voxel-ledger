"""Issuing a bill posts Expense/Tax/AP JE in the same TX (Phase 8.2, #129)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.bill import Bill
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
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
async def test_issue_posts_expense_tax_ap_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_full_ap_stack(app_session, with_tax=True)
    vendor = await seed_vendor(app_session)

    body = sample_bill_body(
        vendor_id=str(vendor.id),
        tax_amount="2.50",
        items=[
            {
                "kind": "manual",
                "description": "Widget supply",
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
    payload = issued.json()
    assert payload["state"] == "issued"
    assert payload["issued_at"] is not None
    assert payload["due_at"] is not None
    je_id = uuid.UUID(payload["posting_journal_entry_id"])

    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == je_id)
        .options(selectinload(JournalEntry.lines))
    )
    je = (await app_session.execute(stmt)).scalar_one()
    lines = sorted(je.lines, key=lambda line: line.line_number)

    by_account = {line.account_id: line for line in lines}
    expense_line = by_account[accounts["expense_account_id"]]
    ap_line = by_account[accounts["ap_account_id"]]
    tax_line = by_account[accounts["tax_account_id"]]

    assert expense_line.debit == Decimal("100.000000")
    assert expense_line.credit == Decimal("0")
    assert tax_line.debit == Decimal("2.500000")
    assert tax_line.credit == Decimal("0")
    assert ap_line.credit == Decimal("102.500000")
    assert ap_line.debit == Decimal("0")

    total_d = sum(line.debit for line in lines)
    total_c = sum(line.credit for line in lines)
    assert total_d == total_c


@pytest.mark.asyncio
async def test_issue_without_tax_omits_tax_line(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_full_ap_stack(app_session, with_tax=False)
    vendor = await seed_vendor(app_session)

    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]

    issued = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])
    stmt = select(JournalLine).where(JournalLine.entry_id == je_id)
    rows = list((await app_session.execute(stmt)).scalars().all())
    assert len(rows) == 2
    account_ids = {r.account_id for r in rows}
    assert accounts["expense_account_id"] in account_ids
    assert accounts["ap_account_id"] in account_ids


@pytest.mark.asyncio
async def test_bill_posting_je_fk_persisted(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_stack(app_session)
    vendor = await seed_vendor(app_session)

    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]
    await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))

    bill = (
        await app_session.execute(select(Bill).where(Bill.id == uuid.UUID(bill_id)))
    ).scalar_one()
    assert bill.posting_journal_entry_id is not None
