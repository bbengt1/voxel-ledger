"""Acquiring a fixed asset enqueues a Dr Asset / Cr Bank QBO outbox posting.

QBO is the sole ledger (epic #312, Phase 5e): a cash acquisition leaves
``posting_journal_entry_id`` None and pushes the balanced posting via
the QBO sync outbox.
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

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_acquire_enqueues_qbo_outbox(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts, cost="2500.00")
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    # QBO is the sole ledger: no local JE is stamped.
    assert payload["posting_journal_entry_id"] is None
    asset_id = uuid.UUID(payload["id"])

    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "fixed_asset_acquisition",
                QboSyncOutbox.local_id == asset_id,
            )
        )
    ).scalar_one()
    assert outbox_row.op == "post"
    lines = outbox_row.payload["lines"]
    by_role = {ln["role"]: ln for ln in lines}
    assert by_role["fixed_asset"]["posting"] == "debit"
    assert Decimal(by_role["fixed_asset"]["amount"]) == Decimal("2500.00")
    assert by_role["bank"]["posting"] == "credit"
    assert Decimal(by_role["bank"]["amount"]) == Decimal("2500.00")
