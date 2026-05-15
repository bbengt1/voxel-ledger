"""Shared helpers for Phase 4.2 journal-entry tests."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Base
from app.models.account import Account
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.models.auth import Role, User
from app.services.auth import create_user
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_open_period(
    session: AsyncSession,
    *,
    name: str = "test-current",
    start_date: date | None = None,
    end_date: date | None = None,
) -> AccountingPeriod:
    """Seed an open accounting period covering "today" (UTC).

    Phase 4.3 requires every journal entry to fall inside an open
    period. Tests that post entries via ``svc.post(...)`` or the HTTP
    endpoint should call this in their setup so the date of ``now_utc()``
    has a matching period.
    """
    today = datetime.now(UTC).date()
    period = AccountingPeriod(
        id=uuid.uuid4(),
        name=name,
        start_date=start_date or date(today.year, 1, 1),
        end_date=end_date or date(today.year, 12, 31),
        state=AccountingPeriodState.OPEN.value,
    )
    session.add(period)
    await session.flush()
    return period


async def seed_owner(session: AsyncSession, email: str = "owner@example.com") -> User:
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.flush()
    # Phase 4.3: every journal post requires an open accounting period
    # covering ``posted_at``. Seed one for "this year" on first call.
    await _ensure_default_period(session)
    return user


async def _ensure_default_period(session: AsyncSession) -> AccountingPeriod:
    from sqlalchemy import select

    existing = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one_or_none()
    if existing is not None:
        return existing
    return await seed_open_period(session)


async def seed_account(
    session: AsyncSession,
    *,
    code: str,
    name: str = "X",
    type: str = "asset",
    is_archived: bool = False,
) -> Account:
    account = Account(
        id=uuid.uuid4(),
        code=code,
        name=name,
        type=type,
        is_archived=is_archived,
    )
    session.add(account)
    await session.flush()
    return account


def now_utc() -> datetime:
    return datetime.now(UTC)


def d(value: str) -> Decimal:
    return Decimal(value)
