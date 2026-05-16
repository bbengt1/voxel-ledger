"""Missing AP posting accounts raise on auto-post (Phase 8.3, #130)."""

from __future__ import annotations

import pytest
from app.models.auth import Role, User
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import (
    auth_header,
    seed_full_ap_payments_stack,
    seed_issued_bill,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_missing_bank_account_setting_blocks_posting(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Auto-post must fail loudly when ap.default_bank_account_id unset."""
    from app.services.settings.service import SettingsService

    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )

    # Unset the bank account setting after seeding
    await SettingsService.set(
        "ap.default_bank_account_id", None, session=app_session, actor_user_id=None
    )
    await app_session.commit()

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "ach",
            "amount": "100.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "100.00"}],
        },
    )
    assert r.status_code == 400, r.text
    assert "ap.default_bank_account_id" in r.json()["detail"]


@pytest.mark.asyncio
async def test_payment_method_to_account_override_used(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Per-method override wins over default_bank_account_id."""
    import uuid

    from app.models.account import Account
    from app.services.settings.service import SettingsService

    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="40.00"
    )

    # Seed a dedicated check-clearing account and route check payments there.
    check_account = Account(id=uuid.uuid4(), code="1015", name="Check Clearing", type="asset")
    app_session.add(check_account)
    await app_session.flush()
    await SettingsService.set(
        "ap.payment_method_to_account",
        {"check": str(check_account.id)},
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(owner),
        json={
            "vendor_id": str(vendor.id),
            "method": "check",
            "amount": "40.00",
            "applications": [{"bill_id": str(bill.id), "amount_applied": "40.00"}],
        },
    )
    assert r.status_code == 201, r.text
    je_id = r.json()["posting_journal_entry_id"]
    assert je_id is not None

    # Verify the credit landed on check_account, not the default bank account.
    from app.models.journal_entry import JournalEntry
    from sqlalchemy.orm import selectinload

    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == uuid.UUID(je_id))
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    credit_accounts = {line.account_id for line in je.lines if line.credit > 0}
    assert check_account.id in credit_accounts
    assert accounts["bank_account_id"] not in credit_accounts
