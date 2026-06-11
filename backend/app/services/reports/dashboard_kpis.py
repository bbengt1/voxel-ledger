"""Dashboard KPI tiles (Phase 10.6, #181; GL tiles retired in #318 Phase 5d).

Single-request roll-up of every tile shown on the dashboard home page.

Cheap enough to call on every dashboard mount — no caching here.
Revisit if the home page starts to feel sluggish (Phase 12 hardening).

Tiles
-----
* ``cash_on_hand`` / ``net_income_mtd`` / ``net_income_ytd`` — **always None**
  since QBO replace-mode (epic #312): these were GL-derived, and the local GL
  stopped receiving postings at cutover. The dashboard renders them as
  "view in QuickBooks". The fields remain so the response shape (and tile
  layout) is stable; they go away entirely with the GL tables in Phase 5f.
* ``accounts_receivable`` — sum ``invoice.amount_outstanding`` for
  invoices in state ``issued / partially_paid / overdue``.
* ``accounts_payable`` — sum ``bill.amount_outstanding`` for bills in
  the same states.
* ``overdue_invoice_count`` / ``overdue_bill_count`` — count of rows
  in state ``overdue``.
* ``low_stock_alert_count`` — count returned by
  :func:`inventory_alerts.list_low_stock`.
* ``last_updated_at`` — wall-clock when the response was built.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill, BillState
from app.models.invoice import Invoice, InvoiceState
from app.services import inventory_alerts as alerts_service

_QUANTUM = Decimal("0.01")

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
    # GL-derived tiles — None in QBO replace-mode (see module docstring).
    cash_on_hand: Decimal | None
    accounts_receivable: Decimal
    accounts_payable: Decimal
    overdue_invoice_count: int
    overdue_bill_count: int
    low_stock_alert_count: int
    net_income_mtd: Decimal | None
    net_income_ytd: Decimal | None
    last_updated_at: datetime


async def build(
    session: AsyncSession,
    *,
    as_of: date | None = None,
) -> DashboardKpis:
    now = datetime.now(UTC)
    asof = as_of or now.date()

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

    return DashboardKpis(
        as_of=asof,
        cash_on_hand=None,
        accounts_receivable=accounts_receivable,
        accounts_payable=accounts_payable,
        overdue_invoice_count=overdue_invoice_count,
        overdue_bill_count=overdue_bill_count,
        low_stock_alert_count=low_stock_alert_count,
        net_income_mtd=None,
        net_income_ytd=None,
        last_updated_at=now,
    )


__all__ = ["DashboardKpis", "build"]
