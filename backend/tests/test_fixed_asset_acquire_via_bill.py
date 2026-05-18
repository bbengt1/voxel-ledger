"""Acquire via bill: no new JE is posted; bill's existing JE is reused (Phase 9.1, #153)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.account import Account
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.models.auth import Role
from app.services import bills as bills_service
from app.services import vendors as vendors_service
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import auth_header, token_for


@pytest.mark.asyncio
async def test_bill_funded_acquisition_reuses_bill_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # --- Seed open period + accounts + settings ---
    today = datetime.now(UTC).date()
    existing = (await app_session.execute(select(AccountingPeriod).limit(1))).scalar_one_or_none()
    if existing is None:
        app_session.add(
            AccountingPeriod(
                id=uuid.uuid4(),
                name="phase91-bill-period",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    asset_acc = Account(id=uuid.uuid4(), code="1500", name="Equipment", type="asset")
    accum = Account(id=uuid.uuid4(), code="1599", name="Accum Dep", type="asset")
    dep_exp = Account(id=uuid.uuid4(), code="6100", name="Dep Exp", type="expense")
    ap_acc = Account(id=uuid.uuid4(), code="2000", name="AP", type="liability")
    fallback_exp = Account(id=uuid.uuid4(), code="5000", name="Expenses", type="expense")
    app_session.add_all([asset_acc, accum, dep_exp, ap_acc, fallback_exp])
    await app_session.flush()
    await SettingsService.set(
        "ap.default_expense_account_id",
        fallback_exp.id,
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "ap.default_ap_account_id",
        ap_acc.id,
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    # --- Seed vendor + bill with override routing to asset_account ---
    vendor = await vendors_service.create(
        app_session,
        display_name="Asset Vendor",
        payment_terms_days=30,
        actor_user_id=None,
    )
    await app_session.commit()

    owner = await token_for(Role.OWNER, client, app_session)

    # Create a draft bill via service routing the expense leg to the
    # asset account (this is the operator's signal that the bill is for
    # acquiring a fixed asset).
    bill = await bills_service.create_draft(
        app_session,
        vendor_id=vendor.id,
        items=[
            {
                "kind": "manual",
                "description": "MacBook Pro",
                "quantity": "1",
                "unit_price": "3000.00",
                "expense_account_id_override": asset_acc.id,
            }
        ],
        actor_user_id=uuid.UUID(int=1),  # any uuid; bill row stores it
    )
    await app_session.commit()

    # Use a real user for issuing (so JE has a real actor_user_id)
    from app.services.auth import create_user

    issuer = await create_user(
        app_session,
        email="bill-issuer@example.com",
        password="pw-correct",
        full_name="Bill Issuer",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    issued_bill = await bills_service.issue(app_session, bill_id=bill.id, actor_user_id=issuer.id)
    await app_session.commit()
    bill_je_id = issued_bill.posting_journal_entry_id
    assert bill_je_id is not None

    # --- Acquire via bill ---
    body = {
        "name": "MacBook Pro 16",
        "kind": "tangible",
        "asset_class": "computer",
        "acquired_on": today.isoformat(),
        "acquisition_cost": "3000.00",
        "salvage_value": "0",
        "useful_life_months": 36,
        "depreciation_method": "straight_line",
        "asset_account_id": str(asset_acc.id),
        "accumulated_depreciation_account_id": str(accum.id),
        "depreciation_expense_account_id": str(dep_exp.id),
        "acquisition_bill_id": str(issued_bill.id),
        "vendor_id": str(vendor.id),
    }
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payload = r.json()

    # Reused bill JE — no fresh JE id.
    assert payload["posting_journal_entry_id"] == str(bill_je_id)


@pytest.mark.asyncio
async def test_bill_without_route_to_asset_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """If the bill has no line whose expense_account_id_override is the
    asset_account_id, the service raises InvalidAcquisitionBillError."""

    today = datetime.now(UTC).date()
    existing = (await app_session.execute(select(AccountingPeriod).limit(1))).scalar_one_or_none()
    if existing is None:
        app_session.add(
            AccountingPeriod(
                id=uuid.uuid4(),
                name="phase91-bill-period-2",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    asset_acc = Account(id=uuid.uuid4(), code="1500", name="Equipment", type="asset")
    accum = Account(id=uuid.uuid4(), code="1599", name="Accum Dep", type="asset")
    dep_exp = Account(id=uuid.uuid4(), code="6100", name="Dep Exp", type="expense")
    ap_acc = Account(id=uuid.uuid4(), code="2000", name="AP", type="liability")
    fallback_exp = Account(id=uuid.uuid4(), code="5000", name="Expenses", type="expense")
    app_session.add_all([asset_acc, accum, dep_exp, ap_acc, fallback_exp])
    await app_session.flush()
    await SettingsService.set(
        "ap.default_expense_account_id",
        fallback_exp.id,
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "ap.default_ap_account_id",
        ap_acc.id,
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    vendor = await vendors_service.create(
        app_session,
        display_name="Other Vendor",
        payment_terms_days=30,
        actor_user_id=None,
    )
    await app_session.commit()

    from app.services.auth import create_user

    issuer = await create_user(
        app_session,
        email="bill-issuer2@example.com",
        password="pw-correct",
        full_name="Issuer",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()

    bill = await bills_service.create_draft(
        app_session,
        vendor_id=vendor.id,
        items=[
            {
                "kind": "manual",
                "description": "General supplies",
                "quantity": "1",
                "unit_price": "3000.00",
            }
        ],
        actor_user_id=issuer.id,
    )
    await app_session.commit()
    await bills_service.issue(app_session, bill_id=bill.id, actor_user_id=issuer.id)
    await app_session.commit()

    owner = await token_for(Role.OWNER, client, app_session)
    body = {
        "name": "Unrouted asset",
        "kind": "tangible",
        "asset_class": "computer",
        "acquired_on": today.isoformat(),
        "acquisition_cost": "3000.00",
        "salvage_value": "0",
        "useful_life_months": 36,
        "depreciation_method": "straight_line",
        "asset_account_id": str(asset_acc.id),
        "accumulated_depreciation_account_id": str(accum.id),
        "depreciation_expense_account_id": str(dep_exp.id),
        "acquisition_bill_id": str(bill.id),
    }
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 400
    assert "routes only" in r.json()["detail"]
