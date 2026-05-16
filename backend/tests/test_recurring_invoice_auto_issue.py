"""Phase 7.5 (#113): auto_issue=true materializes + issues + posts JE."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.invoice import Invoice, InvoiceState
from app.services import recurring_invoices as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import seed_ar_posting_defaults
from tests._recurring_invoices_helpers import create_template, seed_customer, seed_user


@pytest.mark.asyncio
async def test_auto_issue_produces_issued_invoice(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    await seed_ar_posting_defaults(app_session)

    await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
        auto_issue=True,
    )

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert len(created) == 1

    rows = (await app_session.execute(select(Invoice))).scalars().all()
    assert len(rows) == 1
    inv = rows[0]
    assert inv.state == InvoiceState.ISSUED
    assert inv.posting_journal_entry_id is not None
    assert inv.issued_at is not None
