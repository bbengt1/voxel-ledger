"""Budget vs actual variance report (Parity #227).

For an ``accounting_period``, compares the configured ``budget``
rows against the actual journal-line activity in the same date
window. Sign convention matches the income statement:

* revenue (Cr-normal): actual = sum(credit) - sum(debit)
* expense (Dr-normal): actual = sum(debit)  - sum(credit)

For each (account[, division]) slot we report:

* ``budget``   — sum of ``budget.amount`` rows matching the slot.
* ``actual``   — signed activity over the period's date range.
* ``variance`` = actual - budget
* ``variance_pct`` = variance / budget * 100 (None when budget == 0
  to avoid division-by-zero)

Only accounts with either a budget row OR period activity appear.
Grouped by account_type → Revenue / Cost of goods sold / Operating
expenses to match the income statement's sectioning.

Division filter
---------------
When ``division_id`` is set, both the budget side and the actuals
side are filtered to that division. Budget rows with
``division_id IS NULL`` are NEVER included in a per-division run
(they're the catch-all for unallocated, not "applies to every
division").
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
from app.models.accounting_period import AccountingPeriod
from app.models.budget import Budget
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services.settings.service import SettingsService

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VarianceRow:
    account_id: str
    code: str
    name: str
    section: str  # "revenue" | "cogs" | "operating_expenses"
    budget: Decimal
    actual: Decimal
    variance: Decimal
    variance_pct: Decimal | None


@dataclass
class BudgetVarianceReport:
    period_id: str
    period_name: str
    date_from: date
    date_to: date
    division_id: str | None
    revenue_rows: list[VarianceRow] = field(default_factory=list)
    cogs_rows: list[VarianceRow] = field(default_factory=list)
    operating_expense_rows: list[VarianceRow] = field(default_factory=list)
    total_revenue_budget: Decimal = _ZERO
    total_revenue_actual: Decimal = _ZERO
    total_cogs_budget: Decimal = _ZERO
    total_cogs_actual: Decimal = _ZERO
    total_operating_expense_budget: Decimal = _ZERO
    total_operating_expense_actual: Decimal = _ZERO


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


def _variance_pct(
    *, account_type: str, budget: Decimal, actual: Decimal
) -> Decimal | None:
    """``actual - budget`` expressed as a percentage of budget.

    For revenue (Cr-normal) "good" variance is positive (we beat the
    budget). For expense (Dr-normal) "good" variance is negative.
    The caller renders the colour; this function just reports the
    raw math.
    """
    _ = account_type  # reserved for future sign-flipping if needed
    if budget == _ZERO:
        return None
    pct = (actual - budget) / budget * Decimal("100")
    return pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def build(
    session: AsyncSession,
    *,
    period_id: uuid.UUID | str,
    division_id: uuid.UUID | str | None = None,
) -> BudgetVarianceReport:
    if not isinstance(period_id, uuid.UUID):
        period_id = uuid.UUID(str(period_id))
    division_uuid: uuid.UUID | None = None
    if division_id is not None:
        division_uuid = (
            division_id
            if isinstance(division_id, uuid.UUID)
            else uuid.UUID(str(division_id))
        )

    period = (
        await session.execute(
            select(AccountingPeriod).where(AccountingPeriod.id == period_id)
        )
    ).scalar_one_or_none()
    if period is None:
        raise ValueError(f"accounting period {period_id} not found")

    from_dt = datetime.combine(period.start_date, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(period.end_date, datetime.max.time(), tzinfo=UTC)

    # ----- Budget aggregation: sum per account, filtered to the
    # requested division (or all when None).
    budget_stmt = (
        select(
            Budget.account_id,
            func.coalesce(func.sum(Budget.amount), 0).label("amt"),
        )
        .where(Budget.period_id == period.id)
        .group_by(Budget.account_id)
    )
    if division_uuid is not None:
        budget_stmt = budget_stmt.where(Budget.division_id == division_uuid)
    else:
        # When unfiltered, sum ALL budget rows for the period (every
        # division + the catch-all NULL).
        pass
    budgets: dict[uuid.UUID, Decimal] = {
        row[0]: Decimal(str(row[1] or 0))
        for row in (await session.execute(budget_stmt)).all()
    }

    # ----- Actuals: signed activity per account within the period
    # date range. Reversal pairs filtered out.
    base_filter = and_(
        JournalEntry.is_reversed.is_(False),
        JournalEntry.reversal_of_entry_id.is_(None),
    )
    actuals_stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.posted_at >= from_dt)
        .where(JournalEntry.posted_at <= to_dt)
        .where(base_filter)
    )
    if division_uuid is not None:
        actuals_stmt = actuals_stmt.where(JournalLine.division_id == division_uuid)
    actuals_stmt = actuals_stmt.group_by(JournalLine.account_id)
    actuals_raw: dict[uuid.UUID, tuple[Decimal, Decimal]] = {
        row[0]: (Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0)))
        for row in (await session.execute(actuals_stmt)).all()
    }

    touched_ids = set(budgets.keys()) | set(actuals_raw.keys())
    if not touched_ids:
        return BudgetVarianceReport(
            period_id=str(period.id),
            period_name=period.name,
            date_from=period.start_date,
            date_to=period.end_date,
            division_id=str(division_uuid) if division_uuid else None,
        )

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

    report = BudgetVarianceReport(
        period_id=str(period.id),
        period_name=period.name,
        date_from=period.start_date,
        date_to=period.end_date,
        division_id=str(division_uuid) if division_uuid else None,
    )

    for acct in accounts:
        actual_type = (
            acct.type.value if hasattr(acct.type, "value") else acct.type
        )
        dr, cr = actuals_raw.get(acct.id, (_ZERO, _ZERO))
        if actual_type == AccountType.REVENUE.value:
            actual = cr - dr
            section = "revenue"
        else:
            actual = dr - cr
            section = "cogs" if acct.id in cogs_ids else "operating_expenses"
        budget = budgets.get(acct.id, _ZERO)
        if budget == _ZERO and actual == _ZERO:
            continue

        variance = actual - budget
        row = VarianceRow(
            account_id=str(acct.id),
            code=acct.code,
            name=acct.name,
            section=section,
            budget=_q(budget),
            actual=_q(actual),
            variance=_q(variance),
            variance_pct=_variance_pct(
                account_type=actual_type, budget=budget, actual=actual
            ),
        )

        if section == "revenue":
            report.revenue_rows.append(row)
            report.total_revenue_budget += budget
            report.total_revenue_actual += actual
        elif section == "cogs":
            report.cogs_rows.append(row)
            report.total_cogs_budget += budget
            report.total_cogs_actual += actual
        else:
            report.operating_expense_rows.append(row)
            report.total_operating_expense_budget += budget
            report.total_operating_expense_actual += actual

    report.total_revenue_budget = _q(report.total_revenue_budget)
    report.total_revenue_actual = _q(report.total_revenue_actual)
    report.total_cogs_budget = _q(report.total_cogs_budget)
    report.total_cogs_actual = _q(report.total_cogs_actual)
    report.total_operating_expense_budget = _q(report.total_operating_expense_budget)
    report.total_operating_expense_actual = _q(report.total_operating_expense_actual)
    return report


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def to_csv(report: BudgetVarianceReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(
        [
            "section",
            "account_code",
            "account_name",
            "budget",
            "actual",
            "variance",
            "variance_pct",
        ]
    )

    def _emit(label: str, rows: list[VarianceRow]) -> None:
        for row in rows:
            w.writerow(
                [
                    label,
                    row.code,
                    row.name,
                    str(row.budget),
                    str(row.actual),
                    str(row.variance),
                    "" if row.variance_pct is None else str(row.variance_pct),
                ]
            )

    _emit("revenue", report.revenue_rows)
    w.writerow(
        [
            "TOTAL REVENUE",
            "",
            "",
            str(report.total_revenue_budget),
            str(report.total_revenue_actual),
            str(report.total_revenue_actual - report.total_revenue_budget),
            "",
        ]
    )
    _emit("cogs", report.cogs_rows)
    w.writerow(
        [
            "TOTAL COGS",
            "",
            "",
            str(report.total_cogs_budget),
            str(report.total_cogs_actual),
            str(report.total_cogs_actual - report.total_cogs_budget),
            "",
        ]
    )
    _emit("operating_expenses", report.operating_expense_rows)
    w.writerow(
        [
            "TOTAL OPEX",
            "",
            "",
            str(report.total_operating_expense_budget),
            str(report.total_operating_expense_actual),
            str(
                report.total_operating_expense_actual
                - report.total_operating_expense_budget
            ),
            "",
        ]
    )
    return buf.getvalue()


__all__ = [
    "BudgetVarianceReport",
    "VarianceRow",
    "build",
    "to_csv",
]
