"""Headline service-layer test for rates.set_default.

- Create rate A (kind=labor, is_default=true).
- Create rate B (kind=labor, is_default=false).
- Call set_default(B).
- Assert A.is_default = false AND B.is_default = true.
- Assert ``catalog.RateDefaulted`` event payload includes
  ``previous_default_rate_id = A.id``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.event import Event
from app.models.rate import Rate, RateKind
from app.services import rates as rates_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_set_default_flips_atomically_and_emits_event(engine, session: AsyncSession) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    a = await rates_service.create(
        session,
        name="Labor A",
        kind=RateKind.LABOR,
        value=Decimal("25"),
        applies_to_printer_id=None,
        is_default_for_kind=True,
        actor_user_id=None,
    )
    b = await rates_service.create(
        session,
        name="Labor B",
        kind=RateKind.LABOR,
        value=Decimal("30"),
        applies_to_printer_id=None,
        is_default_for_kind=False,
        actor_user_id=None,
    )
    await session.flush()
    assert a.is_default_for_kind is True
    assert b.is_default_for_kind is False

    await rates_service.set_default(session, rate_id=b.id, actor_user_id=None)
    await session.flush()

    refreshed_a = (await session.execute(select(Rate).where(Rate.id == a.id))).scalar_one()
    refreshed_b = (await session.execute(select(Rate).where(Rate.id == b.id))).scalar_one()
    assert refreshed_a.is_default_for_kind is False
    assert refreshed_b.is_default_for_kind is True

    # Find the most recent RateDefaulted event for B.
    defaulted_events = (
        (
            await session.execute(
                select(Event)
                .where(Event.type == "catalog.RateDefaulted")
                .where(Event.aggregate_id == b.id)
                .order_by(Event.position.desc())
            )
        )
        .scalars()
        .all()
    )
    assert defaulted_events, "expected at least one RateDefaulted event for B"
    payload = defaulted_events[0].payload
    assert payload["rate_id"] == str(b.id)
    assert payload["kind"] == "labor"
    assert payload["previous_default_rate_id"] == str(a.id)
