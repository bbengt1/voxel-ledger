"""Shared helpers for tax-profile tests (Phase 9.5, #157)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.account import Account
from app.services import tax as tax_service
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_liability_account(
    session: AsyncSession, *, code: str = "2210", name: str = "Tax Liability"
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type="liability")
    session.add(acct)
    await session.flush()
    return acct


async def seed_tax_profile(
    session: AsyncSession,
    *,
    code: str = "US-CA-COMBINED",
    name: str = "California Combined",
    jurisdiction: str = "US-CA",
    is_reverse_charge: bool = False,
    rates: list[tuple[str, Decimal | str, uuid.UUID, bool]] | None = None,
):
    """Create a tax profile with a list of rates.

    Each rates entry: ``(name, rate, liability_account_id, compound_on_previous)``.
    If ``rates`` is None, a single flat 10% rate is added against a
    freshly-created liability account.
    """
    profile = await tax_service.create_profile(
        session,
        code=code,
        name=name,
        jurisdiction=jurisdiction,
        is_reverse_charge=is_reverse_charge,
        notes=None,
        actor_user_id=None,
    )

    if rates is None:
        acct = await seed_liability_account(session)
        rates = [("Tax", Decimal("0.10"), acct.id, False)]

    for idx, (rname, rate_value, liability_acct_id, compound) in enumerate(rates):
        await tax_service.add_rate(
            session,
            profile_id=profile.id,
            ordinal=idx,
            name=rname,
            rate=Decimal(str(rate_value)),
            liability_account_id=liability_acct_id,
            compound_on_previous=compound,
            actor_user_id=None,
        )
    await session.commit()
    return await tax_service.get_profile(session, profile.id)
