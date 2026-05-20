"""Dashboard KPI tiles (Phase 10.6, #181).

Single-request roll-up of every tile shown on the dashboard home page.

Cheap enough to call on every dashboard mount — no caching here.
Revisit if the home page starts to feel sluggish (Phase 12 hardening).

Tiles
-----
* ``cash_on_hand`` — sum balance (Dr - Cr) of every account in the
  ``reports.cash_accounts`` setting list.
* ``accounts_receivable`` — sum ``invoice.amount_outstanding`` for
  invoices in state ``issued / partially_paid / overdue``.
* ``accounts_payable`` — sum ``bill.amount_outstanding`` for bills in
  the same states.
* ``overdue_invoice_count`` / ``overdue_bill_count`` — count of rows
  in state ``overdue``.
* ``low_stock_alert_count`` — count returned by
  :func:`inventory_alerts.list_low_stock`.
* ``net_income_mtd`` / ``net_income_ytd`` — net income from the
  income-statement service with first-of-month / first-of-year as
  ``date_from``.
* ``last_updated_at`` — wall-clock when the response was built.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill, BillState
from app.models.invoice import Invoice, InvoiceState
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services import inventory_alerts as alerts_service
from app.services.reports import income_statement as income_statement_service
from app.services.settings.service import SettingsService

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")

_OUTSTANDING_STATES_INVOICE = (
    InvoiceState.ISSUED,
    InvoiceState.PARTIALLY_PAID,
    InvoiceState.OVERDUE,
)
_OUTSTANDING_STATES_BILL = (
    BillState.ISSUED,
    BillState.PARTIALLY_PAID,
    BillState.OVERDUE,
)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DashboardKpis:
    as_of: date
    cash_on_hand: Decimal
    accounts_receivable: Decimal
    accounts_payable: Decimal
    overdue_invoice_count: int
    overdue_bill_count: int
    low_stock_alert_count: int
    net_income_mtd: Decimal
    net_income_ytd: Decimal
    last_updated_at: datetime


async def _resolve_cash_account_ids(session: AsyncSession) -> set[uuid.UUID]:
    raw = await SettingsService.get("reports.cash_accounts", session=session)
    if not raw or not isinstance(raw, list):
        return set()
    out: set[uuid.UUID] = set()
    for item in raw:
        if isinstance(item, uuid.UUID):
            out.add(item)
            continue
        try:
            out.add(uuid.UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


async def _cash_on_hand(
    session: AsyncSession,
    *,
    cash_ids: set[uuid.UUID],
    as_of_dt: datetime,
) -> Decimal:
    if not cash_ids:
        return _ZERO
    stmt = (
        select(
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.account_id.in_(list(cash_ids)))
        .where(
            and_(
                JournalEntry.posted_at <= as_of_dt,
                JournalEntry.is_reversed.is_(False),
                JournalEntry.reversal_of_entry_id.is_(None),
            )
        )
    )
    row = (await session.execute(stmt)).one()
    return _q(Decimal(str(row[0] or 0)) - Decimal(str(row[1] or 0)))


async def build(
    session: AsyncSession,
    *,
    as_of: date | None = None,
) -> DashboardKpis:
    now = datetime.now(UTC)
    asof = as_of or now.date()
    as_of_dt = datetime.combine(asof, datetime.max.time(), tzinfo=UTC)

    cash_ids = await _resolve_cash_account_ids(session)
    cash_on_hand = await _cash_on_hand(session, cash_ids=cash_ids, as_of_dt=as_of_dt)

    # AR / AP.
    ar_stmt = select(func.coalesce(func.sum(Invoice.amount_outstanding), 0)).where(
        Invoice.state.in_(_OUTSTANDING_STATES_INVOICE)
    )
    ap_stmt = select(func.coalesce(func.sum(Bill.amount_outstanding), 0)).where(
        Bill.state.in_(_OUTSTANDING_STATES_BILL)
    )
    accounts_receivable = _q(Decimal(str((await session.execute(ar_stmt)).scalar() or 0)))
    accounts_payable = _q(Decimal(str((await session.execute(ap_stmt)).scalar() or 0)))

    # Overdue counts.
    overdue_invoice_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.state == InvoiceState.OVERDUE)
            )
        ).scalar()
        or 0
    )
    overdue_bill_count = int(
        (
            await session.execute(
                select(func.count()).select_from(Bill).where(Bill.state == BillState.OVERDUE)
            )
        ).scalar()
        or 0
    )

    # Low stock alerts.
    alerts = await alerts_service.list_low_stock(session=session)
    low_stock_alert_count = len(alerts)

    # Net income MTD + YTD.
    month_start = date(asof.year, asof.month, 1)
    year_start = date(asof.year, 1, 1)
    mtd = await income_statement_service.build(session, date_from=month_start, date_to=asof)
    ytd = await income_statement_service.build(session, date_from=year_start, date_to=asof)

    return DashboardKpis(
        as_of=asof,
        cash_on_hand=cash_on_hand,
        accounts_receivable=accounts_receivable,
        accounts_payable=accounts_payable,
        overdue_invoice_count=overdue_invoice_count,
        overdue_bill_count=overdue_bill_count,
        low_stock_alert_count=low_stock_alert_count,
        net_income_mtd=mtd.net_income,
        net_income_ytd=ytd.net_income,
        last_updated_at=now,
    )


__all__ = ["DashboardKpis", "build"]
