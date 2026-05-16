"""Phase 7.5 (#113): paused templates do not materialize."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.invoice import Invoice
from app.services import recurring_invoices as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._recurring_invoices_helpers import create_template, seed_customer, seed_user


@pytest.mark.asyncio
async def test_paused_template_skipped(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)

    template = await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await service.pause(app_session, template_id=template.id, actor_user_id=user.id)
    await app_session.commit()

    now = datetime.now(UTC)
    created = await service.materialize_due(session=app_session, now=now)
    await app_session.commit()
    assert created == []

    rows = (await app_session.execute(select(Invoice))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_resume_re_enables_materialize(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)

    template = await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await service.pause(app_session, template_id=template.id, actor_user_id=user.id)
    await app_session.commit()

    # paused → no materialize
    created = await service.materialize_due(session=app_session, now=datetime.now(UTC))
    await app_session.commit()
    assert created == []

    # resume → next tick materializes
    await service.resume(app_session, template_id=template.id, actor_user_id=user.id)
    await app_session.commit()

    created = await service.materialize_due(session=app_session, now=datetime.now(UTC))
    await app_session.commit()
    assert len(created) == 1


@pytest.mark.asyncio
async def test_cancelled_template_skipped(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    template = await create_template(
        app_session,
        customer_id=customer.id,
        actor_user_id=user.id,
        start_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await service.cancel(app_session, template_id=template.id, actor_user_id=user.id)
    await app_session.commit()

    created = await service.materialize_due(session=app_session, now=datetime.now(UTC))
    await app_session.commit()
    assert created == []
