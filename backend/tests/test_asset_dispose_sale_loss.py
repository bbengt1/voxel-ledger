"""Sale at proceeds < book value enqueues a balanced QBO posting with a loss
Dr line (Phase 9.4, #156; QBO-only per epic #312 Phase 5e)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.fixed_asset_disposal import FixedAssetDisposal
from app.models.qbo_sync_outbox import QboSyncOutbox
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._asset_disposal_helpers import (
    mark_entries_posted_up_to,
    seed_gain_loss_account,
    seed_wide_period,
    shift_months,
)
from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_dispose_sale_loss(client: AsyncClient, app_session: AsyncSession) -> None:
    await seed_wide_period(app_session)
    accounts = await seed_acquisition_stack(app_session)
    # Loss side is an expense.
    loss_acct = await seed_gain_loss_account(
        app_session, code="7100", name="Loss on Disposal", kind="expense"
    )
    owner = await token_for(Role.OWNER, client, app_session)

    today = datetime.now(UTC).date()
    body = sample_acquire_body(
        accounts=accounts,
        cost="3600.00",
        acquired_on=shift_months(today, -13).isoformat(),
    )
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    await mark_entries_posted_up_to(app_session, asset_id=asset_id, through_period_index=11)

    dispose_body = {
        "disposed_on": today.isoformat(),
        "kind": "sale",
        "proceeds_amount": "1500.00",  # below the $2400 book value → $900 loss
        "proceeds_account_id": str(accounts["bank_account_id"]),
        "gain_loss_account_id": str(loss_acct.id),
    }
    resp = await client.post(
        f"/api/v1/fixed-assets/{asset_id}/dispose",
        headers=auth_header(owner),
        json=dispose_body,
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert Decimal(payload["gain_loss_amount"]) == Decimal("-900")

    # QBO is the sole ledger (epic #312, Phase 5e): no local JE is stamped;
    # a balanced posting is enqueued on the QBO sync outbox instead.
    assert payload["posting_journal_entry_id"] is None
    disposal = (
        await app_session.execute(
            select(FixedAssetDisposal).where(FixedAssetDisposal.asset_id == asset_id)
        )
    ).scalar_one()
    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "fixed_asset_disposal",
                QboSyncOutbox.local_id == disposal.id,
            )
        )
    ).scalar_one()
    assert outbox_row.op == "post"
    by_role = {
        (ln["role"], ln["posting"]): Decimal(ln["amount"]) for ln in outbox_row.payload["lines"]
    }
    assert by_role[("accumulated_depreciation", "debit")] == Decimal("1200")
    assert by_role[("bank", "debit")] == Decimal("1500")
    assert by_role[("fixed_asset", "credit")] == Decimal("3600")
    # Loss is a Dr to the gain/loss role.
    assert by_role[("gain_loss_on_disposal", "debit")] == Decimal("900")

    total_d = sum(amt for (_, posting), amt in by_role.items() if posting == "debit")
    total_c = sum(amt for (_, posting), amt in by_role.items() if posting == "credit")
    assert total_d == total_c == Decimal("3600")
