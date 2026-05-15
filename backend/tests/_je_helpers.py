"""Shared helpers for Phase 4.2 journal-entry tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models import Base
from app.models.account import Account
from app.models.auth import Role, User
from app.services.auth import create_user
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
    return user


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
