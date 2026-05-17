"""Phase 8.5 (#132): auto_issue=true materializes + issues + posts JE."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.bill import Bill, BillState
from app.services import recurring_bills as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import seed_full_ap_stack
from tests._recurring_bills_helpers import create_template, seed_user, seed_vendor


@pytest.mark.asyncio
async def test_auto_issue_produces_issued_bill(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    vendor = await seed_vendor(app_session)
    await seed_full_ap_stack(app_session)

    await create_template(
        app_session,
        vendor_id=vendor.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
        auto_issue=True,
    )

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert len(created) == 1

    rows = (await app_session.execute(select(Bill))).scalars().all()
    assert len(rows) == 1
    bill = rows[0]
    assert bill.state == BillState.ISSUED
    assert bill.posting_journal_entry_id is not None
    assert bill.issued_at is not None
