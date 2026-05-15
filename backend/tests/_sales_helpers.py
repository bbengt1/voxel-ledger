"""Shared helpers for sales tests (Phase 6.2, #94).

Phase 6.3 (#95) extended the helpers with a ``seed_posting_defaults``
helper that registers default GL accounts + an open accounting period so
tests that confirm a sale don't have to repeat the boilerplate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.auth import Role
from app.services import sales_channels as channels_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_user(session: AsyncSession, *, email: str = "owner@example.com"):
    """Seed an owner user; returns the user row. Useful for service-layer
    tests that need a real ``created_by_user_id`` FK target."""
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    return user


async def seed_channel(
    session: AsyncSession,
    *,
    name: str = "Test channel",
    slug: str = "test-channel",
    kind: str = "marketplace",
    fee_model: str = "percent",
    fee_percent: str | None = "0.05",
    fee_flat: str | None = None,
    default_revenue_account_id: uuid.UUID | None = None,
    default_fee_account_id: uuid.UUID | None = None,
):
    channel = await channels_service.create(
        session,
        name=name,
        slug=slug,
        kind=kind,
        fee_model=fee_model,
        fee_percent=Decimal(fee_percent) if fee_percent else None,
        fee_flat=Decimal(fee_flat) if fee_flat else None,
        default_revenue_account_id=default_revenue_account_id,
        default_fee_account_id=default_fee_account_id,
        actor_user_id=None,
    )
    await session.commit()
    return channel


async def seed_posting_defaults(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None = None,
):
    """Seed all GL accounts + settings + open accounting period needed
    to confirm a sale through the Phase 6.3 COGS service.

    Returns a dict of created entity IDs so tests can target specific
    accounts:

        {
          "cogs_account_id": ...,
          "ar_account_id": ...,
          "revenue_account_id": ...,
          "tax_account_id": ...,
          "fee_account_id": ...,
          "inventory_account_id": ...,
          "channel_id": ...,
        }
    """
    from app.models.account import Account
    from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
    from app.services.settings.service import SettingsService

    today = datetime.now(UTC).date()
    existing_period = await session.execute(
        # local import to avoid top-level overhead
        __import__("sqlalchemy").select(AccountingPeriod).limit(1)
    )
    if existing_period.scalar_one_or_none() is None:
        session.add(
            AccountingPeriod(
                id=uuid.uuid4(),
                name="phase63-test-period",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    inventory_account = Account(id=uuid.uuid4(), code="1300", name="Inventory", type="asset")
    cogs_account = Account(
        id=uuid.uuid4(),
        code="5100",
        name="Cost of Goods Sold",
        type="expense",
    )
    ar_account = Account(id=uuid.uuid4(), code="1200", name="AR", type="asset")
    revenue_account = Account(id=uuid.uuid4(), code="4000", name="Revenue", type="revenue")
    tax_account = Account(id=uuid.uuid4(), code="2200", name="Sales Tax Payable", type="liability")
    fee_account = Account(id=uuid.uuid4(), code="5200", name="Channel Fees", type="expense")
    session.add_all(
        [inventory_account, cogs_account, ar_account, revenue_account, tax_account, fee_account]
    )
    await session.flush()

    await SettingsService.set(
        "sales_posting.cogs_account_id",
        cogs_account.id,
        session=session,
        actor_user_id=actor_user_id,
    )
    await SettingsService.set(
        "sales_posting.default_inventory_account_id",
        inventory_account.id,
        session=session,
        actor_user_id=actor_user_id,
    )
    await SettingsService.set(
        "sales_posting.default_ar_account_id",
        ar_account.id,
        session=session,
        actor_user_id=actor_user_id,
    )
    await SettingsService.set(
        "sales_posting.sales_tax_payable_account_id",
        tax_account.id,
        session=session,
        actor_user_id=actor_user_id,
    )
    await session.commit()
    return {
        "inventory_account_id": inventory_account.id,
        "cogs_account_id": cogs_account.id,
        "ar_account_id": ar_account.id,
        "revenue_account_id": revenue_account.id,
        "tax_account_id": tax_account.id,
        "fee_account_id": fee_account.id,
    }


def sample_sale_body(*, channel_id: str, items: list[dict] | None = None, **extra) -> dict:
    body = {
        "channel_id": channel_id,
        "customer_name": "Test Customer",
        "customer_email": "test@example.com",
        "occurred_at": datetime.now(UTC).isoformat(),
        "discount_amount": "0",
        "shipping_amount": "0",
        "tax_amount": "0",
        "items": items
        if items is not None
        else [
            {
                "kind": "manual",
                "description": "Custom widget",
                "quantity": "2",
                "unit_price": "10.00",
            }
        ],
    }
    body.update(extra)
    return body
