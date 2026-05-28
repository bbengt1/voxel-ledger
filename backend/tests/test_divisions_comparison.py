"""Divisions comparison report tests (Parity #229)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.division import Division
from app.services import journal_entries as journal_service
from app.services.reports import divisions_comparison as report_service
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
    jls = [
        journal_service.JournalLineInput(
            account_id=acct_id,
            debit=d(dr),
            credit=d(cr),
            line_number=i,
            division_id=div,
        )
        for i, (acct_id, dr, cr, div) in enumerate(lines, start=1)
    ]
    return await journal_service.post(
        journal_service.JournalEntryInput(description=description, posted_at=posted_at, lines=jls),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )


async def _seed_division(session: AsyncSession, *, code: str, name: str) -> Division:
    div = Division(id=uuid.uuid4(), code=code, name=name)
    session.add(div)
    await session.flush()
    return div


@pytest.mark.asyncio
async def test_side_by_side_columns_per_division_plus_unallocated(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Two divisions + one tagged + one untagged JE → 3 columns
    (the two divisions + an unallocated). Revenue + expense totals
    split correctly per column."""
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    cogs = await seed_account(app_session, code="5000", name="COGS", type="expense")
    div_a = await _seed_division(app_session, code="A", name="Alpha")
    div_b = await _seed_division(app_session, code="B", name="Bravo")
    await app_session.commit()

    today = datetime.now(UTC)
    # $100 sale tagged Alpha + $40 cogs tagged Alpha.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Alpha sale",
        posted_at=today,
        lines=[
            (bank.id, "100.00", "0", div_a.id),
            (rev.id, "0", "100.00", div_a.id),
        ],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Alpha COGS",
        posted_at=today,
        lines=[
            (cogs.id, "40.00", "0", div_a.id),
            (bank.id, "0", "40.00", div_a.id),
        ],
    )
    # $250 sale tagged Bravo.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Bravo sale",
        posted_at=today,
        lines=[
            (bank.id, "250.00", "0", div_b.id),
            (rev.id, "0", "250.00", div_b.id),
        ],
    )
    # $30 sale with no division (unallocated).
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Unallocated sale",
        posted_at=today,
        lines=[
            (bank.id, "30.00", "0", None),
            (rev.id, "0", "30.00", None),
        ],
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )

    column_ids = [c.division_id for c in report.columns]
    # Real divisions sorted by code, unallocated last.
    assert column_ids == [
        str(div_a.id),
        str(div_b.id),
        report_service.UNALLOCATED_COLUMN_ID,
    ]
    # Revenue per column:
    assert report.total_revenue[str(div_a.id)] == Decimal("100.00")
    assert report.total_revenue[str(div_b.id)] == Decimal("250.00")
    assert report.total_revenue[report_service.UNALLOCATED_COLUMN_ID] == Decimal("30.00")
    # Only Alpha had expense.
    alpha_opex = report.total_operating_expenses[str(div_a.id)]
    bravo_opex = report.total_operating_expenses[str(div_b.id)]
    assert alpha_opex == Decimal("40.00")
    assert bravo_opex == Decimal("0.00")
    # Net income = revenue - cogs - opex; no cogs ids set → 5000 lands
    # under operating expenses.
    assert report.net_income[str(div_a.id)] == Decimal("60.00")
    assert report.net_income[str(div_b.id)] == Decimal("250.00")
    assert report.net_income[report_service.UNALLOCATED_COLUMN_ID] == Decimal("30.00")


@pytest.mark.asyncio
async def test_archived_divisions_excluded(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Rev", type="revenue")
    live = await _seed_division(app_session, code="LIVE", name="Live")
    archived = await _seed_division(app_session, code="ARCH", name="Archived")
    archived.is_archived = True
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=datetime.now(UTC).date(),
        date_to=datetime.now(UTC).date(),
    )
    _ = (user, bank, rev)  # unused but seeded so the test exercises the lookup
    ids = [c.division_id for c in report.columns]
    assert str(live.id) in ids
    assert str(archived.id) not in ids


@pytest.mark.asyncio
async def test_csv_includes_every_column_and_totals(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    div_a = await _seed_division(app_session, code="A", name="Alpha")
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[
            (bank.id, "100.00", "0", div_a.id),
            (rev.id, "0", "100.00", div_a.id),
        ],
    )
    await app_session.commit()

    report = await report_service.build(app_session, date_from=today.date(), date_to=today.date())
    csv_body = report_service.to_csv(report)
    assert "TOTAL REVENUE" in csv_body
    assert "NET INCOME" in csv_body
    assert "100.00" in csv_body
    # Header row carries our division code + label.
    assert "A:Alpha" in csv_body or "Alpha" in csv_body


@pytest.mark.asyncio
async def test_endpoint_smoke(client: AsyncClient, app_session: AsyncSession) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    today = datetime.now(UTC)
    token = await token_for(Role.OWNER, client, app_session)
    resp = await client.get(
        "/api/v1/reports/divisions-comparison",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "date_from": today.date().isoformat(),
            "date_to": today.date().isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # An empty install still produces the unallocated column.
    column_ids = [c["division_id"] for c in body["columns"]]
    assert "__unallocated__" in column_ids
