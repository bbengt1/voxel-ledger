"""Voiding a bill enqueues the QBO reverse + void guards (Phase 8.2, #129).

QBO is the sole ledger (epic #312, Phase 5e).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.bill import Bill
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
async def test_void_enqueues_qbo_reverse(client: AsyncClient, app_session: AsyncSession) -> None:
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
    # QBO is the sole ledger: no local JE.
    assert issued.json()["posting_journal_entry_id"] is None

    void = await client.post(f"/api/v1/bills/{bill_id}/void", headers=auth_header(owner))
    assert void.status_code == 200, void.text
    assert void.json()["state"] == "void"

    # Issue enqueued op=post; void enqueued op=reverse.
    rows = (
        (
            await app_session.execute(
                select(QboSyncOutbox)
                .where(
                    QboSyncOutbox.kind == "bill",
                    QboSyncOutbox.local_id == uuid.UUID(bill_id),
                )
                .order_by(QboSyncOutbox.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [row.op for row in rows] == ["post", "reverse"]


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
