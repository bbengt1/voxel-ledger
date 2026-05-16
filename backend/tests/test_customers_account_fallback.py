"""Customer account-default fallback chain (Phase 7.1, #109).

``resolve_default_revenue_account`` walks customer -> channel -> settings.
``resolve_default_ar_account`` walks customer -> (channel skip) -> settings.
"""

from __future__ import annotations

import uuid

import pytest
from app.models import Base
from app.models.account import Account
from app.services import customers as customers_service
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel


@pytest.fixture(autouse=True)
async def _create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _make_account(
    session: AsyncSession, *, code: str, name: str, type_: str = "asset"
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type=type_)
    session.add(acct)
    await session.flush()
    return acct


async def _make_customer(
    session: AsyncSession,
    *,
    default_revenue_account_id: uuid.UUID | None = None,
    default_ar_account_id: uuid.UUID | None = None,
):
    return await customers_service.create(
        session,
        display_name="Acme Co.",
        default_revenue_account_id=default_revenue_account_id,
        default_ar_account_id=default_ar_account_id,
        actor_user_id=None,
    )


@pytest.mark.asyncio
async def test_revenue_chain_customer_wins(session: AsyncSession):
    customer_revenue = await _make_account(session, code="4001", name="Cust Rev", type_="revenue")
    channel_revenue = await _make_account(session, code="4002", name="Chan Rev", type_="revenue")
    channel = await seed_channel(session, default_revenue_account_id=channel_revenue.id)
    customer = await _make_customer(session, default_revenue_account_id=customer_revenue.id)
    resolved = await customers_service.resolve_default_revenue_account(
        customer, channel=channel, session=session
    )
    assert resolved == customer_revenue.id


@pytest.mark.asyncio
async def test_revenue_chain_falls_back_to_channel(session: AsyncSession):
    channel_revenue = await _make_account(session, code="4002", name="Chan Rev", type_="revenue")
    channel = await seed_channel(session, default_revenue_account_id=channel_revenue.id)
    customer = await _make_customer(session)
    resolved = await customers_service.resolve_default_revenue_account(
        customer, channel=channel, session=session
    )
    assert resolved == channel_revenue.id


@pytest.mark.asyncio
async def test_revenue_chain_falls_back_to_setting(session: AsyncSession):
    settings_ar = await _make_account(session, code="1200", name="AR control")
    channel = await seed_channel(session)  # no default_revenue_account_id
    customer = await _make_customer(session)
    await SettingsService.set(
        "sales_posting.default_ar_account_id",
        settings_ar.id,
        session=session,
        actor_user_id=None,
    )
    resolved = await customers_service.resolve_default_revenue_account(
        customer, channel=channel, session=session
    )
    assert resolved == settings_ar.id


@pytest.mark.asyncio
async def test_revenue_chain_raises_when_unset(session: AsyncSession):
    channel = await seed_channel(session)
    customer = await _make_customer(session)
    with pytest.raises(customers_service.MissingDefaultAccountError):
        await customers_service.resolve_default_revenue_account(
            customer, channel=channel, session=session
        )


@pytest.mark.asyncio
async def test_ar_chain_customer_wins(session: AsyncSession):
    customer_ar = await _make_account(session, code="1201", name="Cust AR")
    customer = await _make_customer(session, default_ar_account_id=customer_ar.id)
    resolved = await customers_service.resolve_default_ar_account(
        customer, channel=None, session=session
    )
    assert resolved == customer_ar.id


@pytest.mark.asyncio
async def test_ar_chain_falls_back_to_setting(session: AsyncSession):
    settings_ar = await _make_account(session, code="1200", name="AR control")
    customer = await _make_customer(session)
    await SettingsService.set(
        "sales_posting.default_ar_account_id",
        settings_ar.id,
        session=session,
        actor_user_id=None,
    )
    resolved = await customers_service.resolve_default_ar_account(
        customer, channel=None, session=session
    )
    assert resolved == settings_ar.id


@pytest.mark.asyncio
async def test_ar_chain_raises_when_unset(session: AsyncSession):
    customer = await _make_customer(session)
    with pytest.raises(customers_service.MissingDefaultAccountError):
        await customers_service.resolve_default_ar_account(customer, channel=None, session=session)
