"""Budget vs actual variance report tests (Parity #227)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.accounting_period import AccountingPeriod
from app.models.budget import Budget
from app.services import journal_entries as journal_service
from app.services.reports import budget_variance as report_service
from httpx import AsyncClient
from sqlalchemy import select
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
    jls = [
        journal_service.JournalLineInput(
            account_id=acct_id,
            debit=d(dr),
            credit=d(cr),
            line_number=i,
        )
        for i, (acct_id, dr, cr) in enumerate(lines, start=1)
    ]
    return await journal_service.post(
        journal_service.JournalEntryInput(
            description=description, posted_at=posted_at, lines=jls
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )


async def _seed_budget(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    period_id: uuid.UUID,
    amount: str,
    division_id: uuid.UUID | None = None,
) -> Budget:
    b = Budget(
        id=uuid.uuid4(),
        account_id=account_id,
        period_id=period_id,
        division_id=division_id,
        amount=Decimal(amount),
    )
    session.add(b)
    await session.flush()
    return b


@pytest.mark.asyncio
async def test_variance_with_budget_and_actual(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Budget $200 sales, actual $150 → variance -$50, pct -25%.
    Budget $100 opex, actual $120 → variance +$20, pct +20%."""
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    opex = await seed_account(app_session, code="6000", name="Rent", type="expense")
    # The seed already created an open period for the year; grab it.
    period = (await app_session.execute(select(AccountingPeriod))).scalars().first()
    assert period is not None

    await _seed_budget(
        app_session, account_id=rev.id, period_id=period.id, amount="200.00"
    )
    await _seed_budget(
        app_session, account_id=opex.id, period_id=period.id, amount="100.00"
    )
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "150.00", "0"), (rev.id, "0", "150.00")],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Rent",
        posted_at=today,
        lines=[(opex.id, "120.00", "0"), (bank.id, "0", "120.00")],
    )
    await app_session.commit()

    report = await report_service.build(app_session, period_id=period.id)

    rev_row = report.revenue_rows[0]
    assert rev_row.budget == Decimal("200.00")
    assert rev_row.actual == Decimal("150.00")
    assert rev_row.variance == Decimal("-50.00")
    assert rev_row.variance_pct == Decimal("-25.00")

    opex_row = report.operating_expense_rows[0]
    assert opex_row.budget == Decimal("100.00")
    assert opex_row.actual == Decimal("120.00")
    assert opex_row.variance == Decimal("20.00")
    assert opex_row.variance_pct == Decimal("20.00")


@pytest.mark.asyncio
async def test_zero_budget_yields_null_pct(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """When budget == 0 we can't divide; variance_pct must be None."""
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    period = (await app_session.execute(select(AccountingPeriod))).scalars().first()
    assert period is not None
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "50.00", "0"), (rev.id, "0", "50.00")],
    )
    await app_session.commit()

    report = await report_service.build(app_session, period_id=period.id)
    # No budget row exists → the actual still shows up.
    assert len(report.revenue_rows) == 1
    row = report.revenue_rows[0]
    assert row.budget == Decimal("0.00")
    assert row.actual == Decimal("50.00")
    assert row.variance == Decimal("50.00")
    assert row.variance_pct is None


@pytest.mark.asyncio
async def test_account_with_no_activity_and_no_budget_excluded(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_owner(app_session)
    await seed_account(app_session, code="4000", name="Sales", type="revenue")
    period = (await app_session.execute(select(AccountingPeriod))).scalars().first()
    assert period is not None
    await app_session.commit()

    report = await report_service.build(app_session, period_id=period.id)
    assert report.revenue_rows == []
    assert report.operating_expense_rows == []


@pytest.mark.asyncio
async def test_csv_round_trip(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    period = (await app_session.execute(select(AccountingPeriod))).scalars().first()
    assert period is not None
    await _seed_budget(
        app_session, account_id=rev.id, period_id=period.id, amount="100.00"
    )
    await app_session.commit()

    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "75.00", "0"), (rev.id, "0", "75.00")],
    )
    await app_session.commit()

    report = await report_service.build(app_session, period_id=period.id)
    body = report_service.to_csv(report)
    assert "section" in body
    assert "TOTAL REVENUE" in body
    assert "75.00" in body
    assert "100.00" in body


@pytest.mark.asyncio
async def test_endpoint_smoke(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    from datetime import date as date_cls

    from app.models.accounting_period import AccountingPeriodState
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    # token_for already seeds the owner user; seed only the period
    # here (token_for doesn't open one).
    period = AccountingPeriod(
        id=uuid.uuid4(),
        name="smoke",
        start_date=date_cls(2026, 1, 1),
        end_date=date_cls(2026, 12, 31),
        state=AccountingPeriodState.OPEN.value,
    )
    app_session.add(period)
    await app_session.commit()
    token = await token_for(Role.OWNER, client, app_session)
    resp = await client.get(
        "/api/v1/reports/budget-variance",
        headers={"Authorization": f"Bearer {token}"},
        params={"period_id": str(period.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period_id"] == str(period.id)
    assert "revenue_rows" in body
