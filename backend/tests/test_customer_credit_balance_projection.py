"""Customer credit balance: accrue 100 + apply 30 -> 70; replay-determinism (Phase 7.4, #112)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.events.types import ar as ar_events
from app.models import Base
from app.models.customer_credit import CustomerCreditBalance
from app.schemas.events import EventCreate
from app.services import event_store
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.mark.asyncio
async def test_accrue_then_apply_yields_70() -> None:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)

    customer_id = uuid.uuid4()

    async with factory() as session:
        await event_store.append(
            EventCreate(
                type=ar_events.TYPE_CUSTOMER_CREDIT_ACCRUED,
                aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER_CREDIT,
                aggregate_id=customer_id,
                payload={
                    "customer_id": str(customer_id),
                    "transaction_id": str(uuid.uuid4()),
                    "amount": "100.00",
                },
                occurred_at=datetime.now(UTC),
                correlation_id=uuid.uuid4(),
                actor_user_id=None,
            ),
            session=session,
        )
        await session.commit()

    async with factory() as session:
        await event_store.append(
            EventCreate(
                type=ar_events.TYPE_CUSTOMER_CREDIT_APPLIED,
                aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER_CREDIT,
                aggregate_id=customer_id,
                payload={
                    "customer_id": str(customer_id),
                    "transaction_id": str(uuid.uuid4()),
                    "amount": "30.00",
                },
                occurred_at=datetime.now(UTC),
                correlation_id=uuid.uuid4(),
                actor_user_id=None,
            ),
            session=session,
        )
        await session.commit()

    async with factory() as session:
        bal = (
            await session.execute(
                select(CustomerCreditBalance).where(
                    CustomerCreditBalance.customer_id == customer_id
                )
            )
        ).scalar_one()
        assert bal.available_amount == Decimal("70.000000")

    await eng.dispose()


@pytest.mark.asyncio
async def test_replay_is_deterministic() -> None:
    """Replay the same two events again -> balance doubles to 140 only
    if applied AGAIN; deleting + replaying yields 70 again.

    The projection is idempotent over the SAME event stream. We
    truncate the read model and replay the projection handlers against
    the existing event log; the resulting balance must equal what live
    appending produced.
    """
    from app.models.event import Event
    from app.projections.customer_credit.handlers import (
        project_customer_credit_accrued,
        project_customer_credit_applied,
    )

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)

    customer_id = uuid.uuid4()
    async with factory() as session:
        for amt, typ in (
            ("100.00", ar_events.TYPE_CUSTOMER_CREDIT_ACCRUED),
            ("30.00", ar_events.TYPE_CUSTOMER_CREDIT_APPLIED),
        ):
            await event_store.append(
                EventCreate(
                    type=typ,
                    aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER_CREDIT,
                    aggregate_id=customer_id,
                    payload={
                        "customer_id": str(customer_id),
                        "transaction_id": str(uuid.uuid4()),
                        "amount": amt,
                    },
                    occurred_at=datetime.now(UTC),
                    correlation_id=uuid.uuid4(),
                    actor_user_id=None,
                ),
                session=session,
            )
        await session.commit()

    # Truncate read model + replay
    async with factory() as session:
        await session.execute(CustomerCreditBalance.__table__.delete())
        await session.commit()

    async with factory() as session:
        events = (
            (
                await session.execute(
                    select(Event)
                    .where(
                        Event.type.in_(
                            [
                                ar_events.TYPE_CUSTOMER_CREDIT_ACCRUED,
                                ar_events.TYPE_CUSTOMER_CREDIT_APPLIED,
                            ]
                        )
                    )
                    .order_by(Event.position)
                )
            )
            .scalars()
            .all()
        )
        for ev in events:
            if ev.type == ar_events.TYPE_CUSTOMER_CREDIT_ACCRUED:
                await project_customer_credit_accrued(ev, session)
            else:
                await project_customer_credit_applied(ev, session)
        await session.commit()

    async with factory() as session:
        bal = (
            await session.execute(
                select(CustomerCreditBalance).where(
                    CustomerCreditBalance.customer_id == customer_id
                )
            )
        ).scalar_one()
        assert bal.available_amount == Decimal("70.000000")

    await eng.dispose()
