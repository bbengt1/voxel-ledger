"""Phase 8.5 (#132): materialize_due behavior + idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.bill import Bill, BillState
from app.services import recurring_bills as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._recurring_bills_helpers import create_template, seed_user, seed_vendor


@pytest.mark.asyncio
async def test_only_due_templates_materialize(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    vendor = await seed_vendor(app_session)

    due = await create_template(
        app_session,
        vendor_id=vendor.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
        name="due",
    )
    not_due = await create_template(
        app_session,
        vendor_id=vendor.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) + timedelta(days=7),
        name="future",
    )

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()

    assert len(created) == 1
    bill_ids = {str(b.id) for b in created}

    refreshed_due = await service.get(app_session, due.id)
    refreshed_not_due = await service.get(app_session, not_due.id)

    assert refreshed_due.last_issued_at is not None
    assert refreshed_due.next_issue_at > now
    assert refreshed_not_due.last_issued_at is None

    rows = (await app_session.execute(select(Bill))).scalars().all()
    assert len(rows) == 1
    assert str(rows[0].id) in bill_ids
    assert rows[0].state == BillState.DRAFT


@pytest.mark.asyncio
async def test_idempotent_re_run_same_now(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    vendor = await seed_vendor(app_session)

    await create_template(
        app_session,
        vendor_id=vendor.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
    )

    now = datetime.now(UTC)
    first = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert len(first) == 1

    second = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert second == []

    rows = (await app_session.execute(select(Bill))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_catch_up_advances_past_now(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    vendor = await seed_vendor(app_session)
    template = await create_template(
        app_session,
        vendor_id=vendor.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(days=3),
        cadence_kind="daily",
    )

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert len(created) == 1

    refreshed = await service.get(app_session, template.id)
    assert refreshed.next_issue_at > now
