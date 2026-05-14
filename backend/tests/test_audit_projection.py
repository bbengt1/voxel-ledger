"""Wildcard audit-log projection: every event → one row."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.events.types import auth as auth_events
from app.models import Base
from app.models.audit import AuditLog
from app.models.auth import Role
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.auth import create_user
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_appending_any_event_writes_audit_row(engine, session: AsyncSession) -> None:
    await _setup_schema(engine)
    ev_id = uuid.uuid4()
    await event_store.append(
        EventCreate(
            type="test.TestEvent",
            aggregate_type="test",
            aggregate_id=ev_id,
            payload={"value": "hello"},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
        ),
        session=session,
    )
    await session.commit()

    rows = list((await session.execute(select(AuditLog))).scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "test.TestEvent"
    assert row.aggregate_type == "test"
    assert row.aggregate_id == ev_id
    assert row.event_position == 1


@pytest.mark.asyncio
async def test_actor_denormalization(engine, session: AsyncSession) -> None:
    await _setup_schema(engine)
    user = await create_user(
        session,
        email="audit-actor@example.com",
        password="pw-correct",
        full_name="Audit Actor",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.flush()

    await event_store.append(
        EventCreate(
            type=auth_events.TYPE_LOGIN_SUCCEEDED,
            aggregate_type="user",
            aggregate_id=user.id,
            payload={
                "email": user.email,
                "user_id": str(user.id),
                "ip": "203.0.113.7",
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=user.id,
        ),
        session=session,
    )
    await session.commit()

    row = (await session.execute(select(AuditLog))).scalar_one()
    assert row.actor_email == "audit-actor@example.com"
    assert row.actor_role == "owner"
    assert row.ip_address == "203.0.113.7"
    assert row.payload_excerpt == {"email": "audit-actor@example.com"}
    assert "audit-actor@example.com" in row.summary


@pytest.mark.asyncio
async def test_audit_row_idempotent_on_replay(engine, session: AsyncSession) -> None:
    """Calling the handler twice for the same event is a no-op (replay-safe)."""
    await _setup_schema(engine)
    await event_store.append(
        EventCreate(
            type="test.TestEvent",
            aggregate_type="test",
            aggregate_id=uuid.uuid4(),
            payload={"value": "v"},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
        ),
        session=session,
    )
    await session.commit()

    # Get the event and re-run the projection.
    from app.models.event import Event
    from app.projections.audit.handler import project_audit

    ev = (await session.execute(select(Event))).scalar_one()
    await project_audit(ev, session)  # should be a no-op
    await session.commit()

    rows = list((await session.execute(select(AuditLog))).scalars().all())
    assert len(rows) == 1
