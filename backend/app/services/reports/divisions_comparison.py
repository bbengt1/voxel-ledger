"""Divisions comparison report (Parity #229).

Side-by-side income statement for every active division in a single
window. A "(unallocated)" column captures the lines that have no
``division_id`` set — useful for the operator to see whether the
unallocated pile is large enough to warrant tagging.

Aggregation
-----------
One pass over ``journal_line``: GROUP BY ``(account_id, division_id)``
inside the date window, filter reversal pairs the same way
:mod:`app.services.reports.income_statement` does. The result is then
pivoted into one row per account with one column per active division
plus the unallocated column.

Sign convention matches the income statement:
* revenue (Cr-normal): amount = sum(credit) - sum(debit)
* expense (Dr-normal): amount = sum(debit)  - sum(credit)

Sections (revenue / cogs / operating expenses) match the income
statement's COGS classification driven by
``reports.cogs_account_ids``.
"""

from __future__ import annotations

import io
import uuid
from csv import writer as csv_writer
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.division import Division
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services.settings.service import SettingsService

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")

# Constant column-id for the "unallocated" pseudo-division. Stays
# stable across runs so the frontend can target it explicitly.
UNALLOCATED_COLUMN_ID: str = "__unallocated__"


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonColumn:
    """One column of the side-by-side report.

    For real divisions, ``division_id`` is the row id and ``label``
    is the human-readable name. The pseudo "unallocated" column uses
    :data:`UNALLOCATED_COLUMN_ID` and the label ``"(unallocated)"``.
    """

    division_id: str
    code: str
    label: str


@dataclass(frozen=True)
class ComparisonRow:
    account_id: str
    code: str
    name: str
    section: str  # "revenue" | "cogs" | "operating_expenses"
    # column-id -> signed amount (Decimal, quantized to 2dp).
    amounts: dict[str, Decimal]


@dataclass
class DivisionsComparisonReport:
    date_from: date
    date_to: date
    columns: list[ComparisonColumn]
    revenue_rows: list[ComparisonRow] = field(default_factory=list)
    cogs_rows: list[ComparisonRow] = field(default_factory=list)
    operating_expense_rows: list[ComparisonRow] = field(default_factory=list)
    # Per-column footer totals.
    total_revenue: dict[str, Decimal] = field(default_factory=dict)
    total_cogs: dict[str, Decimal] = field(default_factory=dict)
    gross_profit: dict[str, Decimal] = field(default_factory=dict)
    total_operating_expenses: dict[str, Decimal] = field(default_factory=dict)
    operating_income: dict[str, Decimal] = field(default_factory=dict)
    net_income: dict[str, Decimal] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


async def _resolve_cogs_account_ids(session: AsyncSession) -> frozenset[uuid.UUID]:
    raw = await SettingsService.get("reports.cogs_account_ids", session=session)
    if not raw:
        return frozenset()
    out: set[uuid.UUID] = set()
    for value in raw:
        if isinstance(value, uuid.UUID):
            out.add(value)
            continue
        try:
            out.add(uuid.UUID(str(value)))
        except (ValueError, TypeError):
            continue
    return frozenset(out)


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
) -> DivisionsComparisonReport:
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    # 1. Columns: every non-archived division + the unallocated pseudo.
    divisions = list(
        (
            await session.execute(
                select(Division)
                .where(Division.is_archived.is_(False))
                .order_by(Division.code.asc())
            )
        )
        .scalars()
        .all()
    )
    columns: list[ComparisonColumn] = [
        ComparisonColumn(
            division_id=str(d.id),
            code=d.code,
            label=d.name,
        )
        for d in divisions
    ]
    columns.append(
        ComparisonColumn(
            division_id=UNALLOCATED_COLUMN_ID,
            code="",
            label="(unallocated)",
        )
    )

    # 2. One pass: GROUP BY (account_id, division_id).
    base_filter = and_(
        JournalEntry.is_reversed.is_(False),
        JournalEntry.reversal_of_entry_id.is_(None),
    )
    stmt = (
        select(
            JournalLine.account_id,
            JournalLine.division_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.posted_at >= from_dt)
        .where(JournalEntry.posted_at <= to_dt)
        .where(base_filter)
        .group_by(JournalLine.account_id, JournalLine.division_id)
    )
    rows = list((await session.execute(stmt)).all())

    # Pivot: per-(account_id, column_id) signed amount.
    per_acct: dict[uuid.UUID, dict[str, Decimal]] = {}
    for acct_id, div_id, dr, cr in rows:
        bucket = per_acct.setdefault(acct_id, {})
        col_id = str(div_id) if div_id is not None else UNALLOCATED_COLUMN_ID
        prev_dr, prev_cr = bucket.get(f"{col_id}__raw", (_ZERO, _ZERO))
        bucket[f"{col_id}__raw"] = (
            prev_dr + Decimal(str(dr or 0)),
            prev_cr + Decimal(str(cr or 0)),
        )

    # 3. Fetch account metadata for every touched account.
    touched_ids = set(per_acct.keys())
    accounts: list[Account] = []
    if touched_ids:
        accounts = list(
            (
                await session.execute(
                    select(Account)
                    .where(Account.id.in_(touched_ids))
                    .where(
                        Account.type.in_(
                            [
                                AccountType.REVENUE.value,
                                AccountType.EXPENSE.value,
                            ]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
    accounts.sort(key=lambda a: a.code)

    cogs_ids = await _resolve_cogs_account_ids(session)

    # 4. Build per-section rows.
    column_ids = [c.division_id for c in columns]
    report = DivisionsComparisonReport(
        date_from=date_from, date_to=date_to, columns=columns
    )
    for col_id in column_ids:
        report.total_revenue[col_id] = _ZERO
        report.total_cogs[col_id] = _ZERO
        report.total_operating_expenses[col_id] = _ZERO

    for acct in accounts:
        actual_type = (
            acct.type.value if hasattr(acct.type, "value") else acct.type
        )
        bucket = per_acct.get(acct.id, {})
        amounts: dict[str, Decimal] = {}
        for col_id in column_ids:
            dr, cr = bucket.get(f"{col_id}__raw", (_ZERO, _ZERO))
            amount = (
                cr - dr if actual_type == AccountType.REVENUE.value else dr - cr
            )
            amounts[col_id] = _q(amount)

        if not any(v != _ZERO for v in amounts.values()):
            continue

        if actual_type == AccountType.REVENUE.value:
            section = "revenue"
        elif acct.id in cogs_ids:
            section = "cogs"
        else:
            section = "operating_expenses"

        row = ComparisonRow(
            account_id=str(acct.id),
            code=acct.code,
            name=acct.name,
            section=section,
            amounts=amounts,
        )
        if section == "revenue":
            report.revenue_rows.append(row)
            for col_id, amt in amounts.items():
                report.total_revenue[col_id] += amt
        elif section == "cogs":
            report.cogs_rows.append(row)
            for col_id, amt in amounts.items():
                report.total_cogs[col_id] += amt
        else:
            report.operating_expense_rows.append(row)
            for col_id, amt in amounts.items():
                report.total_operating_expenses[col_id] += amt

    # Derived totals per column.
    for col_id in column_ids:
        rev = _q(report.total_revenue[col_id])
        cogs = _q(report.total_cogs[col_id])
        opex = _q(report.total_operating_expenses[col_id])
        gross = _q(rev - cogs)
        op_income = _q(gross - opex)
        report.total_revenue[col_id] = rev
        report.total_cogs[col_id] = cogs
        report.total_operating_expenses[col_id] = opex
        report.gross_profit[col_id] = gross
        report.operating_income[col_id] = op_income
        # Net income = operating income; no non-operating sections here
        # (matches the income-statement service's current shape).
        report.net_income[col_id] = op_income
    return report


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def to_csv(report: DivisionsComparisonReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    header = ["section", "account_code", "account_name"] + [
        f"{c.code}:{c.label}" if c.code else c.label for c in report.columns
    ]
    w.writerow(header)

    def _emit_section(label: str, rows: list[ComparisonRow]) -> None:
        for row in rows:
            w.writerow(
                [
                    label,
                    row.code,
                    row.name,
                    *[str(row.amounts.get(c.division_id, _ZERO)) for c in report.columns],
                ]
            )

    _emit_section("revenue", report.revenue_rows)
    w.writerow(
        [
            "TOTAL REVENUE",
            "",
            "",
            *[str(report.total_revenue[c.division_id]) for c in report.columns],
        ]
    )
    _emit_section("cogs", report.cogs_rows)
    w.writerow(
        ["TOTAL COGS", "", "", *[str(report.total_cogs[c.division_id]) for c in report.columns]]
    )
    w.writerow(
        ["GROSS PROFIT", "", "", *[str(report.gross_profit[c.division_id]) for c in report.columns]]
    )
    _emit_section("operating_expenses", report.operating_expense_rows)
    w.writerow(
        [
            "TOTAL OPERATING EXPENSES",
            "",
            "",
            *[str(report.total_operating_expenses[c.division_id]) for c in report.columns],
        ]
    )
    w.writerow(
        [
            "NET INCOME",
            "",
            "",
            *[str(report.net_income[c.division_id]) for c in report.columns],
        ]
    )
    return buf.getvalue()


__all__ = [
    "ComparisonColumn",
    "ComparisonRow",
    "DivisionsComparisonReport",
    "UNALLOCATED_COLUMN_ID",
    "build",
    "to_csv",
]
