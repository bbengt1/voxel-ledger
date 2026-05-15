"""Shared helpers for Phase 4.4 approval-workflow tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.auth import Role, User
from app.services.approvals import ApprovalsService
from app.services.auth import create_user
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    role: Role = Role.OWNER,
) -> User:
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=email.split("@")[0],
        role=role,
        bcrypt_rounds=4,
    )
    await session.flush()
    return user


async def make_pending(
    session: AsyncSession,
    *,
    requester: User,
    payload: dict[str, Any] | None = None,
    request_type: str = "accounting.large_journal_entry",
    subject_kind: str = "journal_entry",
    threshold: Decimal | None = Decimal("1000.00"),
):
    return await ApprovalsService.create(
        request_type=request_type,
        subject_kind=subject_kind,
        subject_id=uuid.uuid4(),
        payload=payload or {"sample": "data"},
        threshold_amount=threshold,
        session=session,
        actor_user_id=requester.id,
    )


def now_utc() -> datetime:
    return datetime.now(UTC)
