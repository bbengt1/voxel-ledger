"""Balance sheet report tests (Phase 10.2, #177)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.services import journal_entries as journal_service
from app.services.reports import balance_sheet as report_service
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
async def test_identity_holds(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    ap = await seed_account(app_session, code="2000", name="AP", type="liability")
    equity = await seed_account(app_session, code="3000", name="Owner equity", type="equity")
    await app_session.commit()

    today = datetime.now(UTC)
    # Owner contributes $1000 cash: Dr Bank 1000 / Cr Equity 1000
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Owner contribution",
        posted_at=today,
        lines=[(bank.id, "1000.00", "0"), (equity.id, "0", "1000.00")],
    )
    # Buy on credit: Dr Bank 200 / Cr AP 200 (cash advance)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Cash advance",
        posted_at=today,
        lines=[(bank.id, "200.00", "0"), (ap.id, "0", "200.00")],
    )
    await app_session.commit()

    report = await report_service.build(app_session, as_of=today.date())
    assert report.total_assets == Decimal("1200.00")
    assert report.total_liabilities == Decimal("200.00")
    assert report.total_equity == Decimal("1000.00")
    assert report.total_liabilities_and_equity == Decimal("1200.00")
    assert report.imbalance == Decimal("0.00")


@pytest.mark.asyncio
async def test_excludes_entries_after_as_of(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    equity = await seed_account(app_session, code="3000", name="Owner equity", type="equity")
    await app_session.commit()

    today = datetime.now(UTC)
    # Entry today.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Today",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (equity.id, "0", "100.00")],
    )
    # Entry tomorrow.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Tomorrow",
        posted_at=today + timedelta(days=2),
        lines=[(bank.id, "50.00", "0"), (equity.id, "0", "50.00")],
    )
    await app_session.commit()

    report = await report_service.build(app_session, as_of=today.date())
    # Only the first entry should count.
    assert report.total_assets == Decimal("100.00")


@pytest.mark.asyncio
async def test_retained_earnings_rollup(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    re_acct = await seed_account(app_session, code="3900", name="Retained earnings", type="equity")
    await app_session.commit()

    today = datetime.now(UTC)
    # Cash sale: Dr Bank 100 / Cr Sales 100 → revenue raises P&L, asset side raises bank.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Cash sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (revenue.id, "0", "100.00")],
    )
    await app_session.commit()

    # Without RE setting: asset = 100, L+E = 0, imbalance = 100.
    report = await report_service.build(app_session, as_of=today.date())
    assert report.total_assets == Decimal("100.00")
    assert report.imbalance == Decimal("100.00")

    # With RE setting: asset 100, equity 100 (synthetic), imbalance 0.
    await SettingsService.set(
        "reports.retained_earnings_account_id",
        str(re_acct.id),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    report2 = await report_service.build(app_session, as_of=today.date())
    assert report2.total_equity == Decimal("100.00")
    assert report2.imbalance == Decimal("0.00")


@pytest.mark.asyncio
async def test_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    equity = await seed_account(app_session, code="3000", name="Owner equity", type="equity")
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Contribution",
        posted_at=today,
        lines=[(bank.id, "10.00", "0"), (equity.id, "0", "10.00")],
    )
    await app_session.commit()

    report = await report_service.build(app_session, as_of=today.date())
    csv = report_service.to_csv(report)
    rows = csv.strip().splitlines()
    assert rows[0].split(",")[0] == "section"
    assert any("LIABILITIES + EQUITY" in line for line in rows)
    assert any("IMBALANCE" in line for line in rows)
