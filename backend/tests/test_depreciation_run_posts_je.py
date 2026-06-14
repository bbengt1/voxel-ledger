"""Depreciation run enqueues a QBO outbox posting per planned entry.

QBO is the sole ledger (epic #312, Phase 5e): the run flips entries to
``posted``, leaves ``journal_entry_id`` None, and pushes a balanced
role-tagged posting via the QBO sync outbox.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.models.fixed_asset import FixedAsset
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.services import depreciation_run as run_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


def _end_of_current_month() -> date:
    today = datetime.now(UTC).date()
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=last)


@pytest.mark.asyncio
async def test_run_enqueues_qbo_outbox(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts, cost="3600.00")  # 36 mo SL = 100/mo
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    period_end = _end_of_current_month()
    result = await run_service.run_for_period(session=app_session, period_end=period_end)
    assert result.posted_count == 1
    assert result.failed_count == 0

    entries = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry)
                .where(DepreciationScheduleEntry.asset_id == asset_id)
                .order_by(DepreciationScheduleEntry.period_index)
            )
        )
        .scalars()
        .all()
    )
    posted = [e for e in entries if e.state == DepreciationEntryState.POSTED]
    assert len(posted) == 1
    # QBO is the sole ledger: no local JE is stamped.
    assert posted[0].journal_entry_id is None

    # The posting was enqueued on the QBO sync outbox instead.
    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "depreciation",
                QboSyncOutbox.local_id == posted[0].id,
            )
        )
    ).scalar_one()
    assert outbox_row.op == "post"
    lines = outbox_row.payload["lines"]
    by_role = {ln["role"]: ln for ln in lines}
    assert by_role["depreciation_expense"]["posting"] == "debit"
    assert Decimal(by_role["depreciation_expense"]["amount"]) == Decimal("100")
    assert by_role["accumulated_depreciation"]["posting"] == "credit"
    assert Decimal(by_role["accumulated_depreciation"]["amount"]) == Decimal("100")

    asset = (
        await app_session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one()
    assert asset.last_depreciated_on == posted[0].period_end
