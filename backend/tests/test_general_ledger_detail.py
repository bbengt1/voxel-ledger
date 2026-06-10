"""General-ledger detail report tests (Parity #226)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.services import journal_entries as journal_service
from app.services.reports import general_ledger_detail as gl_service
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
            description=description,
            posted_at=posted_at,
            lines=jls,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_account_opening_lines_closing(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    # Anchor at midday so the +1h/+2h in-window postings below never roll past
    # midnight into the next date (which would drop them from the day-bounded
    # report — a real failure observed when CI runs late in the UTC day).
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=2)
    # Opening: $200 Dr to bank.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Prior",
        posted_at=yesterday,
        lines=[(bank.id, "200.00", "0"), (rev.id, "0", "200.00")],
    )
    # Window: $50 + $30 Dr; one $10 Cr withdrawal.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Window 1",
        posted_at=today,
        lines=[(bank.id, "50.00", "0"), (rev.id, "0", "50.00")],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Window 2",
        posted_at=today + timedelta(hours=1),
        lines=[(bank.id, "30.00", "0"), (rev.id, "0", "30.00")],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Refund",
        posted_at=today + timedelta(hours=2),
        lines=[(rev.id, "10.00", "0"), (bank.id, "0", "10.00")],
    )
    await app_session.commit()

    report = await gl_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
        account_id=bank.id,
    )
    assert len(report.sections) == 1
    sec = report.sections[0]
    assert sec.code == "1000"
    assert sec.opening_balance == Decimal("200.00")
    # 3 in-window lines (asset Dr-normal):
    # 200 + 50 = 250
    # 250 + 30 = 280
    # 280 - 10 = 270
    running = [line.running_balance for line in sec.lines]
    assert running == [Decimal("250.00"), Decimal("280.00"), Decimal("270.00")]
    assert sec.closing_balance == Decimal("270.00")
    assert sec.period_debit == Decimal("80.00")
    assert sec.period_credit == Decimal("10.00")


@pytest.mark.asyncio
async def test_all_accounts_mode_returns_every_touched_account(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    cogs = await seed_account(app_session, code="5000", name="COGS", type="expense")
    await app_session.commit()
    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (rev.id, "0", "100.00")],
    )
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Buy",
        posted_at=today,
        lines=[(cogs.id, "40.00", "0"), (bank.id, "0", "40.00")],
    )
    await app_session.commit()

    report = await gl_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
    )
    codes = [s.code for s in report.sections]
    assert codes == ["1000", "4000", "5000"]


@pytest.mark.asyncio
async def test_date_window_excludes_outside_lines(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()
    today = datetime.now(UTC)
    prior = today - timedelta(days=10)
    future = today + timedelta(days=10)
    for posted_at, desc, amt in (
        (prior, "Prior", "100.00"),
        (today, "Now", "20.00"),
        (future, "Future", "999.00"),
    ):
        await _post_je(
            app_session,
            actor_user_id=user.id,
            description=desc,
            posted_at=posted_at,
            lines=[(bank.id, amt, "0"), (rev.id, "0", amt)],
        )
    await app_session.commit()

    report = await gl_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
        account_id=bank.id,
    )
    sec = report.sections[0]
    # Opening reflects the prior entry.
    assert sec.opening_balance == Decimal("100.00")
    # Only the today line shows up.
    assert len(sec.lines) == 1
    assert sec.lines[0].description == "Now"
    # Closing reflects today, not future.
    assert sec.closing_balance == Decimal("120.00")


@pytest.mark.asyncio
async def test_revenue_running_balance_is_credit_normal(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()
    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (rev.id, "0", "100.00")],
    )
    await app_session.commit()

    report = await gl_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
        account_id=rev.id,
    )
    sec = report.sections[0]
    # Revenue is Cr-normal: a $100 credit moves running from 0 to +100.
    assert sec.lines[0].running_balance == Decimal("100.00")
    assert sec.closing_balance == Decimal("100.00")


@pytest.mark.asyncio
async def test_csv_round_trip(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()
    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (rev.id, "0", "100.00")],
    )
    await app_session.commit()
    report = await gl_service.build(
        app_session,
        date_from=today.date(),
        date_to=today.date(),
    )
    csv_body = gl_service.to_csv(report)
    # Header + opening + line + closing for each of 2 sections.
    assert csv_body.count("\n") >= 7
    assert "account_code" in csv_body
    assert "Opening balance" in csv_body
    assert "Closing balance" in csv_body
    assert "Sale" in csv_body


# ---------------------------------------------------------------------------
# Endpoint smoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_returns_json(client: AsyncClient, app_session: AsyncSession) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    user = await seed_owner(app_session, email="gl@example.com")
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (rev.id, "0", "100.00")],
    )
    await app_session.commit()

    token = await token_for(Role.BOOKKEEPER, client, app_session)
    resp = await client.get(
        "/api/v1/reports/general-ledger-detail",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "date_from": today.date().isoformat(),
            "date_to": today.date().isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    codes = [s["code"] for s in body["sections"]]
    assert "1000" in codes and "4000" in codes


@pytest.mark.asyncio
async def test_endpoint_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    user = await seed_owner(app_session, email="gl-csv@example.com")
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    rev = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    today = datetime.now(UTC)
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (rev.id, "0", "100.00")],
    )
    await app_session.commit()

    token = await token_for(Role.BOOKKEEPER, client, app_session)
    resp = await client.get(
        "/api/v1/reports/general-ledger-detail",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "date_from": today.date().isoformat(),
            "date_to": today.date().isoformat(),
            "format": "csv",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "account_code" in resp.text
