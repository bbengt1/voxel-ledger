"""Recording a tax remittance enqueues a balanced QBO outbox posting in the
same TX (Phase 9.6, #158; QBO-only per epic #312 Phase 5e)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

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
async def test_record_enqueues_qbo_outbox(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_tax_stack(app_session)
    owner, user = await token_for(Role.OWNER, client, app_session)

    # Collect $10 tax on $100 of sales.
    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="100.00",
        tax="10.00",
        actor_user_id=user.id,
    )

    today = datetime.now(UTC).date()
    body = {
        "profile_id": str(accounts["profile_id"]),
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "amount_paid": "10.00",
        "paid_on": today.isoformat(),
        "method": "ach",
        "bank_account_id": str(accounts["bank_account_id"]),
        "reference_number": "EFTPS-12345",
    }
    r = await client.post("/api/v1/tax-remittances", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["state"] == "recorded"
    assert payload["remittance_number"].startswith("TAX-")
    # QBO is the sole ledger (epic #312, Phase 5e): no local JE is stamped.
    assert payload["posting_journal_entry_id"] is None

    remittance_id = uuid.UUID(payload["id"])
    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "tax_remittance",
                QboSyncOutbox.local_id == remittance_id,
            )
        )
    ).scalar_one()
    assert outbox_row.op == "post"
    by_role = {
        (ln["role"], ln["posting"]): Decimal(ln["amount"]) for ln in outbox_row.payload["lines"]
    }
    assert by_role[("tax_liability", "debit")] == Decimal("10")
    assert by_role[("bank", "credit")] == Decimal("10")

    # DB row state
    row = (
        await app_session.execute(select(TaxRemittance).where(TaxRemittance.id == remittance_id))
    ).scalar_one()
    assert row.state == TaxRemittanceState.RECORDED
