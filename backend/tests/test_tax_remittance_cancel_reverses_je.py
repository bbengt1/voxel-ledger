"""Cancelling a tax remittance enqueues a QBO reversal and flips state
(Phase 9.6, #158; QBO-only per epic #312 Phase 5e)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.models.tax_remittance import TaxRemittance, TaxRemittanceState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._tax_remittance_helpers import (
    auth_header,
    post_tax_collection,
    seed_tax_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_cancel_enqueues_qbo_reversal(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_tax_stack(app_session)
    owner, user = await token_for(Role.OWNER, client, app_session)

    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="100.00",
        tax="10.00",
        actor_user_id=user.id,
    )

    today = datetime.now(UTC).date()
    create_body = {
        "profile_id": str(accounts["profile_id"]),
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "amount_paid": "10.00",
        "paid_on": today.isoformat(),
        "method": "ach",
        "bank_account_id": str(accounts["bank_account_id"]),
    }
    created = await client.post(
        "/api/v1/tax-remittances", headers=auth_header(owner), json=create_body
    )
    assert created.status_code == 201
    remittance_id = created.json()["id"]
    # QBO is the sole ledger (epic #312, Phase 5e): no local JE is stamped.
    assert created.json()["posting_journal_entry_id"] is None

    cancel_resp = await client.post(
        f"/api/v1/tax-remittances/{remittance_id}/cancel",
        headers=auth_header(owner),
    )
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert cancel_resp.json()["state"] == "cancelled"

    # A reversal row was enqueued on the QBO sync outbox.
    reverse_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "tax_remittance",
                QboSyncOutbox.local_id == uuid.UUID(remittance_id),
                QboSyncOutbox.op == "reverse",
            )
        )
    ).scalar_one()
    assert reverse_row.payload == {"tax_remittance_id": remittance_id}

    # State on the row
    row = (
        await app_session.execute(
            select(TaxRemittance).where(TaxRemittance.id == uuid.UUID(remittance_id))
        )
    ).scalar_one()
    assert row.state == TaxRemittanceState.CANCELLED

    # Cancel-again is rejected.
    again = await client.post(
        f"/api/v1/tax-remittances/{remittance_id}/cancel",
        headers=auth_header(owner),
    )
    assert again.status_code == 409, again.text
