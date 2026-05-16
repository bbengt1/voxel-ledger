"""Voiding a bill reverses the posted JE (Phase 8.2, #129)."""

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

from tests._bills_helpers import (
    auth_header,
    sample_bill_body,
    seed_full_ap_stack,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_void_reverses_je_net_zero(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_stack(app_session)
    vendor = await seed_vendor(app_session)

    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(
            vendor_id=str(vendor.id),
            tax_amount="1.00",
        ),
    )
    bill_id = create.json()["id"]
    issued = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))
    original_je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])

    void = await client.post(f"/api/v1/bills/{bill_id}/void", headers=auth_header(owner))
    assert void.status_code == 200, void.text
    assert void.json()["state"] == "void"

    original_je = (
        await app_session.execute(select(JournalEntry).where(JournalEntry.id == original_je_id))
    ).scalar_one()
    assert original_je.is_reversed is True

    reversing = (
        await app_session.execute(
            select(JournalEntry).where(JournalEntry.reversal_of_entry_id == original_je_id)
        )
    ).scalar_one()
    all_lines = (
        (
            await app_session.execute(
                select(JournalLine).where(JournalLine.entry_id.in_([original_je.id, reversing.id]))
            )
        )
        .scalars()
        .all()
    )
    total_d = sum(line.debit for line in all_lines)
    total_c = sum(line.credit for line in all_lines)
    assert total_d == total_c
    by_account_d_o = {}
    by_account_c_r = {}
    for line in all_lines:
        if line.entry_id == original_je.id:
            by_account_d_o.setdefault(line.account_id, Decimal("0"))
            by_account_d_o[line.account_id] += line.debit - line.credit
        else:
            by_account_c_r.setdefault(line.account_id, Decimal("0"))
            by_account_c_r[line.account_id] += line.debit - line.credit
    for acct_id, net in by_account_d_o.items():
        assert by_account_c_r[acct_id] == -net, f"account {acct_id} not net zero"


@pytest.mark.asyncio
async def test_void_blocked_when_payments_applied(
    client: AsyncClient, app_session: AsyncSession
) -> None:
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
    bill.amount_paid = Decimal("5.00")
    await app_session.commit()

    void = await client.post(f"/api/v1/bills/{bill_id}/void", headers=auth_header(owner))
    assert void.status_code == 400
    assert "applied payments" in void.json()["detail"]
    assert "Phase 8.3" in void.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_void_paid_bill(client: AsyncClient, app_session: AsyncSession) -> None:
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

    from app.models.bill import BillState

    bill = (
        await app_session.execute(select(Bill).where(Bill.id == uuid.UUID(bill_id)))
    ).scalar_one()
    bill.state = BillState.PAID
    await app_session.commit()

    void = await client.post(f"/api/v1/bills/{bill_id}/void", headers=auth_header(owner))
    assert void.status_code == 400
