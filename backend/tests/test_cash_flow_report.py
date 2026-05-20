"""Cash flow report tests (Phase 10.3, #178)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.services import journal_entries as journal_service
from app.services.reports import cash_flow as report_service
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, seed_account, seed_owner


async def _post_je(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    description: str,
    posted_at: datetime,
    lines: list[tuple[uuid.UUID, str, str]],
):
    journal_lines = [
        journal_service.JournalLineInput(
            account_id=acct_id,
            debit=d(dr),
            credit=d(cr),
            line_number=i,
        )
        for i, (acct_id, dr, cr) in enumerate(lines, start=1)
    ]
    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=description,
            posted_at=posted_at,
            lines=journal_lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    await session.flush()
    return entry


@pytest.mark.asyncio
async def test_starts_at_net_income(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Cash sale",
        posted_at=today,
        lines=[(bank.id, "150.00", "0"), (revenue.id, "0", "150.00")],
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    # First operating line is "Net income" = 150 (revenue, no expenses).
    assert report.operating_lines[0].line_item == "Net income"
    assert report.operating_lines[0].amount == Decimal("150.00")


@pytest.mark.asyncio
async def test_depreciation_add_back(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    asset = await seed_account(app_session, code="1500", name="Equipment", type="asset")
    accum = await seed_account(app_session, code="1599", name="Accumulated dep", type="asset")
    dep_exp = await seed_account(
        app_session, code="6100", name="Depreciation expense", type="expense"
    )
    await app_session.commit()

    today = datetime.now(UTC)
    # Monthly depreciation entry: Dr dep_exp 100 / Cr accum_dep 100.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Depreciation",
        posted_at=today,
        lines=[(dep_exp.id, "100.00", "0"), (accum.id, "0", "100.00")],
    )
    await app_session.commit()

    await SettingsService.set(
        "reports.depreciation_expense_account_ids",
        [str(dep_exp.id)],
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    # Net income = -100 (just expense). Add back 100 → operating_total 0.
    assert report.operating_lines[0].amount == Decimal("-100.00")
    add_back_lines = [line for line in report.operating_lines if "Add back" in line.line_item]
    assert len(add_back_lines) == 1
    assert add_back_lines[0].amount == Decimal("100.00")
    assert report.operating_total == Decimal("0.00")
    # Asset = 0 — silly numerical demo, but unused.
    _ = asset


@pytest.mark.asyncio
async def test_working_capital_delta(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    ar = await seed_account(app_session, code="1100", name="AR", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    today = datetime.now(UTC)
    # Issue an invoice (Dr AR / Cr Sales) — accrual revenue without cash.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Invoice issued",
        posted_at=today,
        lines=[(ar.id, "200.00", "0"), (revenue.id, "0", "200.00")],
    )
    await app_session.commit()

    await SettingsService.set(
        "reports.working_capital_accounts",
        [str(ar.id)],
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "reports.cash_accounts",
        [str(bank.id)],
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    # Net income +200, but AR went up by 200 so operating cash flow is 0.
    assert report.operating_lines[0].amount == Decimal("200.00")
    wc_lines = [line for line in report.operating_lines if line.line_item.startswith("Δ")]
    assert len(wc_lines) == 1
    assert wc_lines[0].amount == Decimal("-200.00")
    assert report.operating_total == Decimal("0.00")
    # Cash didn't move.
    assert report.net_change_in_cash == Decimal("0.00")
    assert report.reconciliation_residual == Decimal("0.00")


@pytest.mark.asyncio
async def test_reconciles_to_delta_cash(client: AsyncClient, app_session: AsyncSession) -> None:
    """Full operating + investing + financing reconciles to Δ cash."""
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    equip = await seed_account(app_session, code="1500", name="Equipment", type="asset")
    loan = await seed_account(app_session, code="2500", name="Loan", type="liability")
    await app_session.commit()

    today = datetime.now(UTC)
    # Cash sale: +100 cash, +100 net income.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (revenue.id, "0", "100.00")],
    )
    # Buy equipment for cash: -50 cash, +50 asset (investing outflow).
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Buy equipment",
        posted_at=today,
        lines=[(equip.id, "50.00", "0"), (bank.id, "0", "50.00")],
    )
    # Borrow: +30 cash, +30 liability (financing inflow).
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Loan draw",
        posted_at=today,
        lines=[(bank.id, "30.00", "0"), (loan.id, "0", "30.00")],
    )
    await app_session.commit()

    await SettingsService.set(
        "reports.investing_accounts",
        [str(equip.id)],
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "reports.financing_accounts",
        [str(loan.id)],
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "reports.cash_accounts",
        [str(bank.id)],
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    # Operating = 100 (net income, no WC).
    # Investing = -50 (equipment bought).
    # Financing = +30 (loan drawn).
    # Δ cash = +80 (100 - 50 + 30).
    assert report.operating_total == Decimal("100.00")
    assert report.investing_total == Decimal("-50.00")
    assert report.financing_total == Decimal("30.00")
    assert report.net_change_in_cash == Decimal("80.00")
    assert report.reconciliation_residual == Decimal("0.00")


@pytest.mark.asyncio
async def test_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "10.00", "0"), (revenue.id, "0", "10.00")],
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    csv = report_service.to_csv(report)
    rows = csv.strip().splitlines()
    assert rows[0].split(",") == ["section", "line_item", "amount"]
    assert any("Net change in cash" in line for line in rows)
    assert any("Residual" in line for line in rows)
