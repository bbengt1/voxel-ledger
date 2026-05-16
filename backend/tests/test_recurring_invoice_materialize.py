"""Phase 7.5 (#113): materialize_due behavior + idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.invoice import Invoice, InvoiceState
from app.services import recurring_invoices as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._recurring_invoices_helpers import create_template, seed_customer, seed_user


@pytest.mark.asyncio
async def test_only_due_templates_materialize(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)

    # Due template (start_at in past)
    due = await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
        name="due",
    )
    # Non-due (start_at in future)
    not_due = await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) + timedelta(days=7),
        name="future",
    )

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()

    assert len(created) == 1
    inv_ids = {str(inv.id) for inv in created}

    # Reload templates
    refreshed_due = await service.get(app_session, due.id)
    refreshed_not_due = await service.get(app_session, not_due.id)

    assert refreshed_due.last_issued_at is not None
    assert refreshed_due.next_issue_at > now
    assert refreshed_not_due.last_issued_at is None

    # The created invoice belongs to the due template's customer
    rows = (await app_session.execute(select(Invoice))).scalars().all()
    assert len(rows) == 1
    assert str(rows[0].id) in inv_ids
    assert rows[0].state == InvoiceState.DRAFT


@pytest.mark.asyncio
async def test_idempotent_re_run_same_now(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)

    await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
    )

    now = datetime.now(UTC)
    first = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert len(first) == 1

    # Re-run with same now → idempotent: next_issue_at already advanced past now
    second = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert second == []

    # Only one invoice in the DB
    rows = (await app_session.execute(select(Invoice))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_catch_up_advances_past_now(client: AsyncClient, app_session: AsyncSession) -> None:
    """A template that was due 3 cycles ago materializes once and the
    new next_issue_at jumps past ``now`` so the next worker tick is a no-op."""
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    # daily cadence, start 3 days ago
    template = await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(days=3),
        cadence_kind="daily",
    )

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert len(created) == 1  # only one invoice per worker tick

    refreshed = await service.get(app_session, template.id)
    assert refreshed.next_issue_at > now
