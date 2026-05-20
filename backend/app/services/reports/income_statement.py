"""Income Statement (P&L) report (Phase 10.1, #176).

Read-only aggregation over ``journal_line`` joined to ``journal_entry``
filtered to ``[date_from, date_to]``. For each account with
``type IN (revenue, expense)``:

* revenue balance  = sum(credit) - sum(debit) (normal balance is Cr)
* expense balance  = sum(debit) - sum(credit) (normal balance is Dr)

Reversal pairs are filtered out: both the original (``is_reversed=true``)
and the reversal entry (``reversal_of_entry_id IS NOT NULL``) drop from
the sum so a posted-then-reversed pair contributes nothing.

COGS classification
-------------------
``account`` has no ``subtype`` column, so the operator configures
``reports.cogs_account_ids`` (list[UUID]) to flag which expense
accounts roll up under "Cost of goods sold" instead of "Operating
expenses". An unconfigured setting puts every expense account in
operating expenses, which is fine for a first-pass report.

Division filter
---------------
``division_id`` narrows on ``journal_line.division_id``. Lines without
a division still match when the filter is unset.

Account hierarchy
-----------------
The report renders a flat list with a ``depth`` integer so the caller
can indent. Depth is computed by walking ``parent_account_id`` from
each touched account up to the root.
"""

from __future__ import annotations

import io
import uuid
from csv import writer as csv_writer
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services.settings.service import SettingsService

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class IncomeStatementRow:
    account_id: str
    code: str
    name: str
    depth: int
    section: str  # "revenue" | "cogs" | "operating_expenses"
    amount: Decimal


@dataclass(frozen=True)
class IncomeStatementReport:
    date_from: date
    date_to: date
    division_id: str | None
    revenue_rows: list[IncomeStatementRow]
    cogs_rows: list[IncomeStatementRow]
    operating_expense_rows: list[IncomeStatementRow]
    total_revenue: Decimal
    total_cogs: Decimal
    gross_profit: Decimal
    total_operating_expenses: Decimal
    operating_income: Decimal
    net_income: Decimal


def _depth(account: Account, by_id: dict[uuid.UUID, Account]) -> int:
    """Walk ``parent_account_id`` to the root; return chain length."""
    depth = 0
    current = account
    seen: set[uuid.UUID] = set()
    while current.parent_account_id is not None:
        if current.parent_account_id in seen:
            break  # defensive — cycle detection lives elsewhere
        seen.add(current.parent_account_id)
        parent = by_id.get(current.parent_account_id)
        if parent is None:
            break
        depth += 1
        current = parent
    return depth


async def _resolve_cogs_account_ids(session: AsyncSession) -> set[uuid.UUID]:
    raw = await SettingsService.get("reports.cogs_account_ids", session=session)
    if not raw:
        return set()
    if isinstance(raw, list):
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
    return set()


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    division_id: uuid.UUID | str | None = None,
) -> IncomeStatementReport:
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    division_uuid: uuid.UUID | None = None
    if division_id is not None:
        division_uuid = (
            division_id if isinstance(division_id, uuid.UUID) else uuid.UUID(str(division_id))
        )

    cogs_ids = await _resolve_cogs_account_ids(session)

    # Pre-load every revenue + expense account so we can render zero-activity
    # accounts in the section but, more importantly, walk ``parent_account_id``
    # for depth.
    accounts_stmt = select(Account).where(
        Account.type.in_([AccountType.REVENUE.value, AccountType.EXPENSE.value])
    )
    accounts = list((await session.execute(accounts_stmt)).scalars().all())
    accounts_by_id = {a.id: a for a in accounts}
    # Also load parents that may sit outside revenue/expense (e.g. a top-level
    # "Income" parent typed as revenue, or an "Operating" group typed as
    # expense — but if anyone's used a non-typed parent, we still want depth).
    parent_ids = {a.parent_account_id for a in accounts if a.parent_account_id is not None}
    missing_parents = parent_ids - set(accounts_by_id.keys())
    if missing_parents:
        extra = (
            (await session.execute(select(Account).where(Account.id.in_(missing_parents))))
            .scalars()
            .all()
        )
        for a in extra:
            accounts_by_id[a.id] = a

    # Single aggregation query: GROUP BY account_id over the joined window.
    je_filter = and_(
        JournalEntry.posted_at >= from_dt,
        JournalEntry.posted_at <= to_dt,
        JournalEntry.is_reversed.is_(False),
        JournalEntry.reversal_of_entry_id.is_(None),
    )
    line_filters = [JournalLine.account_id == Account.id]
    if division_uuid is not None:
        line_filters.append(JournalLine.division_id == division_uuid)

    sums_stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(Account.type.in_([AccountType.REVENUE.value, AccountType.EXPENSE.value]))
        .where(je_filter)
    )
    if division_uuid is not None:
        sums_stmt = sums_stmt.where(JournalLine.division_id == division_uuid)
    sums_stmt = sums_stmt.group_by(JournalLine.account_id)

    sums_rows = list((await session.execute(sums_stmt)).all())
    sums_by_account: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    for account_id, dr, cr in sums_rows:
        sums_by_account[account_id] = (
            Decimal(str(dr or 0)),
            Decimal(str(cr or 0)),
        )

    revenue_rows: list[IncomeStatementRow] = []
    cogs_rows: list[IncomeStatementRow] = []
    operating_rows: list[IncomeStatementRow] = []

    for account in accounts:
        dr, cr = sums_by_account.get(account.id, (_ZERO, _ZERO))
        depth = _depth(account, accounts_by_id)
        actual_type = account.type.value if hasattr(account.type, "value") else account.type
        if actual_type == AccountType.REVENUE.value:
            amount = _q(cr - dr)
            if amount == _ZERO and dr == _ZERO and cr == _ZERO:
                continue  # untouched account
            revenue_rows.append(
                IncomeStatementRow(
                    account_id=str(account.id),
                    code=account.code,
                    name=account.name,
                    depth=depth,
                    section="revenue",
                    amount=amount,
                )
            )
        else:  # expense
            amount = _q(dr - cr)
            if amount == _ZERO and dr == _ZERO and cr == _ZERO:
                continue
            section = "cogs" if account.id in cogs_ids else "operating_expenses"
            row = IncomeStatementRow(
                account_id=str(account.id),
                code=account.code,
                name=account.name,
                depth=depth,
                section=section,
                amount=amount,
            )
            if section == "cogs":
                cogs_rows.append(row)
            else:
                operating_rows.append(row)

    revenue_rows.sort(key=lambda r: r.code)
    cogs_rows.sort(key=lambda r: r.code)
    operating_rows.sort(key=lambda r: r.code)

    total_revenue = _q(sum((r.amount for r in revenue_rows), _ZERO))
    total_cogs = _q(sum((r.amount for r in cogs_rows), _ZERO))
    gross_profit = _q(total_revenue - total_cogs)
    total_operating = _q(sum((r.amount for r in operating_rows), _ZERO))
    operating_income = _q(gross_profit - total_operating)
    net_income = operating_income  # No "other income" rollup yet.

    return IncomeStatementReport(
        date_from=date_from,
        date_to=date_to,
        division_id=str(division_uuid) if division_uuid is not None else None,
        revenue_rows=revenue_rows,
        cogs_rows=cogs_rows,
        operating_expense_rows=operating_rows,
        total_revenue=total_revenue,
        total_cogs=total_cogs,
        gross_profit=gross_profit,
        total_operating_expenses=total_operating,
        operating_income=operating_income,
        net_income=net_income,
    )


def to_csv(report: IncomeStatementReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(["section", "account_code", "account_name", "depth", "amount"])
    for r in report.revenue_rows:
        w.writerow(["Revenue", r.code, r.name, r.depth, str(r.amount)])
    w.writerow(["Revenue", "TOTAL", "", "", str(report.total_revenue)])
    for r in report.cogs_rows:
        w.writerow(["Cost of goods sold", r.code, r.name, r.depth, str(r.amount)])
    w.writerow(["Cost of goods sold", "TOTAL", "", "", str(report.total_cogs)])
    w.writerow(["Totals", "GROSS PROFIT", "", "", str(report.gross_profit)])
    for r in report.operating_expense_rows:
        w.writerow(["Operating expenses", r.code, r.name, r.depth, str(r.amount)])
    w.writerow(["Operating expenses", "TOTAL", "", "", str(report.total_operating_expenses)])
    w.writerow(["Totals", "OPERATING INCOME", "", "", str(report.operating_income)])
    w.writerow(["Totals", "NET INCOME", "", "", str(report.net_income)])
    return buf.getvalue()


__all__ = [
    "IncomeStatementReport",
    "IncomeStatementRow",
    "build",
    "to_csv",
]
