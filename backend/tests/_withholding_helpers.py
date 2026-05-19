"""Shared helpers for withholding-profile tests (Phase 9.7, #159)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.account import Account
from app.models.vendor import Vendor
from app.models.withholding_profile import WithholdingProfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_withholding_liability_account(
    session: AsyncSession,
    *,
    code: str = "2110",
    name: str = "1099 Withholding Payable",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type="liability")
    session.add(acct)
    await session.flush()
    await session.commit()
    return acct


async def seed_withholding_profile(
    session: AsyncSession,
    *,
    liability_account_id: uuid.UUID,
    code: str = "US-1099-NEC",
    rate: Decimal | str = "0.07",
    threshold_per_year: Decimal | str | None = None,
    form_kind: str | None = "1099-NEC",
) -> WithholdingProfile:
    profile = WithholdingProfile(
        id=uuid.uuid4(),
        code=code,
        name="US 1099-NEC backup withholding",
        jurisdiction="US",
        rate=Decimal(str(rate)),
        liability_account_id=liability_account_id,
        threshold_per_year=(
            Decimal(str(threshold_per_year)) if threshold_per_year is not None else None
        ),
        form_kind=form_kind,
        is_active=True,
    )
    session.add(profile)
    await session.flush()
    await session.commit()
    return profile


async def attach_profile_to_vendor(
    session: AsyncSession, *, vendor_id: uuid.UUID, profile_id: uuid.UUID
) -> None:
    vendor = (await session.execute(select(Vendor).where(Vendor.id == vendor_id))).scalar_one()
    vendor.withholding_profile_id = profile_id
    await session.flush()
    await session.commit()
