"""Cash Flow report (indirect method) — Phase 10.3, #178.

Walks from net income to net change in cash:

1. **Operating** — start with net income from the income statement,
   add back non-cash items (depreciation + amortization expense), then
   walk working-capital changes for the period.
2. **Investing** — period activity on the investing-account set.
3. **Financing** — period activity on the financing-account set.
4. **Reconciliation** — actual Δ cash for the period and the residual
   ``(operating + investing + financing) - delta_cash``. Non-zero
   means the account-set configuration is incomplete or activity
   exists outside the configured sets — surfaced rather than hidden.

Sign convention
---------------
For every account class, *cash impact of period activity* equals
``sum(credit) - sum(debit)``:

* asset: Dr increases the asset (cash consumed = negative); Cr
  decreases it (cash freed = positive).
* liability / equity: Cr increases it (cash inflow = positive); Dr
  decreases it (cash outflow = negative).

Both signs collapse into ``Cr - Dr`` of the activity in the window.

For cash itself (an asset), Δ balance = Dr - Cr (period activity).
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterable
from csv import writer as csv_writer
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services.reports import income_statement as income_statement_service
from app.services.settings.service import SettingsService

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CashFlowLine:
    section: str  # "operating" | "investing" | "financing" | "reconciliation"
    line_item: str
    amount: Decimal


@dataclass(frozen=True)
class CashFlowReport:
    date_from: date
    date_to: date
    division_id: str | None
    operating_lines: list[CashFlowLine]
    operating_total: Decimal
    investing_lines: list[CashFlowLine]
    investing_total: Decimal
    financing_lines: list[CashFlowLine]
    financing_total: Decimal
    net_change_in_cash: Decimal
    reconciliation_residual: Decimal


async def _resolve_uuid_list(session: AsyncSession, key: str) -> set[uuid.UUID]:
    raw = await SettingsService.get(key, session=session)
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


async def _period_activity_by_account(
    session: AsyncSession,
    *,
    account_ids: Iterable[uuid.UUID],
    from_dt: datetime,
    to_dt: datetime,
    division_uuid: uuid.UUID | None,
) -> dict[uuid.UUID, tuple[Decimal, Decimal, Account]]:
    """Return ``{account_id: (period_debit, period_credit, account)}``."""
    ids = list(account_ids)
    if not ids:
        return {}
    je_filter = and_(
        JournalEntry.posted_at >= from_dt,
        JournalEntry.posted_at <= to_dt,
        JournalEntry.is_reversed.is_(False),
        JournalEntry.reversal_of_entry_id.is_(None),
    )
    sums_stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.account_id.in_(ids))
        .where(je_filter)
    )
    if division_uuid is not None:
        sums_stmt = sums_stmt.where(JournalLine.division_id == division_uuid)
    sums_stmt = sums_stmt.group_by(JournalLine.account_id)
    sums = {
        row[0]: (Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0)))
        for row in (await session.execute(sums_stmt)).all()
    }

    accounts_stmt = select(Account).where(Account.id.in_(ids))
    accounts = {a.id: a for a in (await session.execute(accounts_stmt)).scalars().all()}

    out: dict[uuid.UUID, tuple[Decimal, Decimal, Account]] = {}
    for acct_id in ids:
        acct = accounts.get(acct_id)
        if acct is None:
            continue
        dr, cr = sums.get(acct_id, (_ZERO, _ZERO))
        out[acct_id] = (dr, cr, acct)
    return out


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    division_id: uuid.UUID | str | None = None,
) -> CashFlowReport:
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    division_uuid: uuid.UUID | None = None
    if division_id is not None:
        division_uuid = (
            division_id if isinstance(division_id, uuid.UUID) else uuid.UUID(str(division_id))
        )

    # --- 1. Net income from the income-statement service. ---
    pnl = await income_statement_service.build(
        session,
        date_from=date_from,
        date_to=date_to,
        division_id=division_uuid,
    )
    net_income = pnl.net_income

    # --- Resolve every account-set setting in parallel-ish. ---
    dep_ids = await _resolve_uuid_list(session, "reports.depreciation_expense_account_ids")
    wc_ids = await _resolve_uuid_list(session, "reports.working_capital_accounts")
    inv_ids = await _resolve_uuid_list(session, "reports.investing_accounts")
    fin_ids = await _resolve_uuid_list(session, "reports.financing_accounts")
    cash_ids = await _resolve_uuid_list(session, "reports.cash_accounts")

    operating_lines: list[CashFlowLine] = [
        CashFlowLine(section="operating", line_item="Net income", amount=_q(net_income))
    ]
    operating_total = _q(net_income)

    # --- 2. Add back depreciation + amortization (non-cash expense). ---
    if dep_ids:
        dep_activity = await _period_activity_by_account(
            session,
            account_ids=dep_ids,
            from_dt=from_dt,
            to_dt=to_dt,
            division_uuid=division_uuid,
        )
        for _acct_id, (dr, cr, acct) in sorted(dep_activity.items(), key=lambda kv: kv[1][2].code):
            # Expense add-back = Dr - Cr (the expense recognized in the period).
            add_back = _q(dr - cr)
            if add_back == _ZERO:
                continue
            operating_lines.append(
                CashFlowLine(
                    section="operating",
                    line_item=f"Add back: {acct.code} {acct.name}",
                    amount=add_back,
                )
            )
            operating_total += add_back

    # --- 3. Working-capital changes. ---
    if wc_ids:
        wc_activity = await _period_activity_by_account(
            session,
            account_ids=wc_ids,
            from_dt=from_dt,
            to_dt=to_dt,
            division_uuid=division_uuid,
        )
        for _acct_id, (dr, cr, acct) in sorted(wc_activity.items(), key=lambda kv: kv[1][2].code):
            cash_impact = _q(cr - dr)
            if cash_impact == _ZERO:
                continue
            operating_lines.append(
                CashFlowLine(
                    section="operating",
                    line_item=f"Δ {acct.code} {acct.name}",
                    amount=cash_impact,
                )
            )
            operating_total += cash_impact

    operating_total = _q(operating_total)

    # --- 4. Investing. ---
    investing_lines: list[CashFlowLine] = []
    if inv_ids:
        inv_activity = await _period_activity_by_account(
            session,
            account_ids=inv_ids,
            from_dt=from_dt,
            to_dt=to_dt,
            division_uuid=division_uuid,
        )
        for _acct_id, (dr, cr, acct) in sorted(inv_activity.items(), key=lambda kv: kv[1][2].code):
            cash_impact = _q(cr - dr)
            if cash_impact == _ZERO:
                continue
            investing_lines.append(
                CashFlowLine(
                    section="investing",
                    line_item=f"{acct.code} {acct.name}",
                    amount=cash_impact,
                )
            )
    investing_total = _q(sum((line.amount for line in investing_lines), _ZERO))

    # --- 5. Financing. ---
    financing_lines: list[CashFlowLine] = []
    if fin_ids:
        fin_activity = await _period_activity_by_account(
            session,
            account_ids=fin_ids,
            from_dt=from_dt,
            to_dt=to_dt,
            division_uuid=division_uuid,
        )
        for _acct_id, (dr, cr, acct) in sorted(fin_activity.items(), key=lambda kv: kv[1][2].code):
            cash_impact = _q(cr - dr)
            if cash_impact == _ZERO:
                continue
            financing_lines.append(
                CashFlowLine(
                    section="financing",
                    line_item=f"{acct.code} {acct.name}",
                    amount=cash_impact,
                )
            )
    financing_total = _q(sum((line.amount for line in financing_lines), _ZERO))

    # --- 6. Cash. ---
    net_change_in_cash = _ZERO
    if cash_ids:
        cash_activity = await _period_activity_by_account(
            session,
            account_ids=cash_ids,
            from_dt=from_dt,
            to_dt=to_dt,
            division_uuid=division_uuid,
        )
        for _acct_id, (dr, cr, _acct) in cash_activity.items():
            net_change_in_cash += dr - cr  # asset Δ = Dr - Cr.
    net_change_in_cash = _q(net_change_in_cash)

    reconciliation = _q(operating_total + investing_total + financing_total - net_change_in_cash)

    return CashFlowReport(
        date_from=date_from,
        date_to=date_to,
        division_id=str(division_uuid) if division_uuid is not None else None,
        operating_lines=operating_lines,
        operating_total=operating_total,
        investing_lines=investing_lines,
        investing_total=investing_total,
        financing_lines=financing_lines,
        financing_total=financing_total,
        net_change_in_cash=net_change_in_cash,
        reconciliation_residual=reconciliation,
    )


def to_csv(report: CashFlowReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(["section", "line_item", "amount"])
    for line in report.operating_lines:
        w.writerow(["Operating", line.line_item, str(line.amount)])
    w.writerow(["Operating", "TOTAL", str(report.operating_total)])
    for line in report.investing_lines:
        w.writerow(["Investing", line.line_item, str(line.amount)])
    w.writerow(["Investing", "TOTAL", str(report.investing_total)])
    for line in report.financing_lines:
        w.writerow(["Financing", line.line_item, str(line.amount)])
    w.writerow(["Financing", "TOTAL", str(report.financing_total)])
    w.writerow(["Reconciliation", "Net change in cash", str(report.net_change_in_cash)])
    w.writerow(["Reconciliation", "Residual", str(report.reconciliation_residual)])
    return buf.getvalue()


__all__ = [
    "CashFlowLine",
    "CashFlowReport",
    "build",
    "to_csv",
]
