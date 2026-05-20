"""Income statement (P&L) report tests (Phase 10.1, #176)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.services import journal_entries as journal_service
from app.services.reports import income_statement as report_service
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
    lines: list[tuple[uuid.UUID, str, str, uuid.UUID | None]],
):
    """Post a balanced JE. ``lines`` items: (account_id, debit, credit, division_id?)."""
    journal_lines = [
        journal_service.JournalLineInput(
            account_id=acct_id,
            debit=d(dr),
            credit=d(cr),
            line_number=i,
            division_id=div_id,
        )
        for i, (acct_id, dr, cr, div_id) in enumerate(lines, start=1)
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
async def test_buckets_by_type(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    cogs = await seed_account(app_session, code="5000", name="COGS", type="expense")
    rent = await seed_account(app_session, code="5100", name="Rent", type="expense")
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale 1",
        posted_at=today,
        lines=[(bank.id, "100.00", "0", None), (revenue.id, "0", "100.00", None)],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Pay rent",
        posted_at=today,
        lines=[(rent.id, "40.00", "0", None), (bank.id, "0", "40.00", None)],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="COGS post",
        posted_at=today,
        lines=[(cogs.id, "30.00", "0", None), (bank.id, "0", "30.00", None)],
    )
    await SettingsService.set(
        "reports.cogs_account_ids",
        [str(cogs.id)],
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    assert report.total_revenue == Decimal("100.00")
    assert report.total_cogs == Decimal("30.00")
    assert report.gross_profit == Decimal("70.00")
    assert report.total_operating_expenses == Decimal("40.00")
    assert report.operating_income == Decimal("30.00")
    assert report.net_income == Decimal("30.00")
    assert [r.code for r in report.revenue_rows] == ["4000"]
    assert [r.code for r in report.cogs_rows] == ["5000"]
    assert [r.code for r in report.operating_expense_rows] == ["5100"]


@pytest.mark.asyncio
async def test_excludes_reversed_pair(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    today = datetime.now(UTC)
    entry = await _post_je(
        app_session,
        actor_user_id=user.id,
        description="To be reversed",
        posted_at=today,
        lines=[(bank.id, "55.00", "0", None), (revenue.id, "0", "55.00", None)],
    )
    await app_session.commit()
    await journal_service.reverse(entry.id, session=app_session, actor_user_id=user.id)
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    assert report.total_revenue == Decimal("0.00")


@pytest.mark.asyncio
async def test_division_filter(client: AsyncClient, app_session: AsyncSession) -> None:
    from app.models.division import Division

    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    div_a = Division(id=uuid.uuid4(), code="A", name="Div A", is_archived=False)
    div_b = Division(id=uuid.uuid4(), code="B", name="Div B", is_archived=False)
    app_session.add_all([div_a, div_b])
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="A sale",
        posted_at=today,
        lines=[(bank.id, "60.00", "0", div_a.id), (revenue.id, "0", "60.00", div_a.id)],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="B sale",
        posted_at=today,
        lines=[(bank.id, "40.00", "0", div_b.id), (revenue.id, "0", "40.00", div_b.id)],
    )
    await app_session.commit()

    report_all = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    assert report_all.total_revenue == Decimal("100.00")

    report_a = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
        division_id=div_a.id,
    )
    assert report_a.total_revenue == Decimal("60.00")


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
        lines=[(bank.id, "10.00", "0", None), (revenue.id, "0", "10.00", None)],
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    csv = report_service.to_csv(report)
    lines = csv.strip().splitlines()
    assert lines[0].split(",")[0] == "section"
    assert any("NET INCOME" in line for line in lines)
    assert any("Sales" in line for line in lines)
