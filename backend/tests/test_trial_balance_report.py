"""Trial balance report tests (Phase 10.4, #179)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.services import journal_entries as journal_service
from app.services.reports import trial_balance as report_service
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
async def test_period_totals_balance(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    expense = await seed_account(app_session, code="5000", name="COGS", type="expense")
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (revenue.id, "0", "100.00")],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Buy supplies",
        posted_at=today,
        lines=[(expense.id, "40.00", "0"), (bank.id, "0", "40.00")],
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    assert report.total_period_debit == report.total_period_credit == Decimal("140.00")
    # Three touched accounts, sorted by code.
    assert [r.code for r in report.rows] == ["1000", "4000", "5000"]


@pytest.mark.asyncio
async def test_opening_excludes_in_window_entries(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    today = datetime.now(UTC)
    yesterday = today - timedelta(days=2)
    # Yesterday: $200 (opening).
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Prior sale",
        posted_at=yesterday,
        lines=[(bank.id, "200.00", "0"), (revenue.id, "0", "200.00")],
    )
    # Today: $50 in the window.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Window sale",
        posted_at=today,
        lines=[(bank.id, "50.00", "0"), (revenue.id, "0", "50.00")],
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
    )
    bank_row = next(r for r in report.rows if r.code == "1000")
    # Opening = $200 Dr (asset normal Dr), period_debit = $50, closing = $250.
    assert bank_row.opening_balance == Decimal("200.00")
    assert bank_row.period_debit == Decimal("50.00")
    assert bank_row.closing_balance == Decimal("250.00")


@pytest.mark.asyncio
async def test_include_zero_widens_to_full_coa(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    # Never-touched account.
    untouched = await seed_account(app_session, code="9999", name="Untouched", type="expense")
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

    narrow = await report_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
    )
    assert untouched.id not in {uuid.UUID(r.account_id) for r in narrow.rows}

    wide = await report_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
        include_zero=True,
    )
    assert untouched.id in {uuid.UUID(r.account_id) for r in wide.rows}


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
        date_from=today.date(),
        date_to=today.date(),
    )
    csv = report_service.to_csv(report)
    rows = csv.strip().splitlines()
    assert rows[0].split(",") == [
        "account_code",
        "account_name",
        "opening",
        "period_debit",
        "period_credit",
        "closing",
    ]
    assert any(line.startswith("GRAND TOTAL,") for line in rows)
