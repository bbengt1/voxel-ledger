"""Trial Balance report (Phase 10.4, #179).

For each account touched in ``[period_start, period_end]`` (or every
COA account when ``include_zero=True``), reports:

* ``opening_balance`` — signed balance from entries strictly before
  ``period_start``.
* ``period_debit`` / ``period_credit`` — raw sums of debits and
  credits in the window.
* ``closing_balance`` — opening plus the period activity, signed by
  account type.

Sign convention
---------------
* asset / expense (normal Dr): balance = sum(debit) - sum(credit).
* liability / equity / revenue (normal Cr): balance = sum(credit) - sum(debit).

The grand-total row sums ``period_debit`` and ``period_credit``; the
``total_debit == total_credit`` invariant is the integrity check the
operator looks at.

Reversal pairs are filtered out (matches the income-statement +
balance-sheet approach).
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

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")

_DR_NORMAL: frozenset[str] = frozenset({AccountType.ASSET.value, AccountType.EXPENSE.value})


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _signed_balance(account_type: str, debit: Decimal, credit: Decimal) -> Decimal:
    if account_type in _DR_NORMAL:
        return debit - credit
    return credit - debit


@dataclass(frozen=True)
class TrialBalanceRow:
    account_id: str
    code: str
    name: str
    type: str
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class TrialBalanceReport:
    date_from: date
    date_to: date
    division_id: str | None
    include_zero: bool
    rows: list[TrialBalanceRow]
    total_period_debit: Decimal
    total_period_credit: Decimal


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    division_id: uuid.UUID | str | None = None,
    include_zero: bool = False,
) -> TrialBalanceReport:
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    division_uuid: uuid.UUID | None = None
    if division_id is not None:
        division_uuid = (
            division_id if isinstance(division_id, uuid.UUID) else uuid.UUID(str(division_id))
        )

    base_je_filter = and_(
        JournalEntry.is_reversed.is_(False),
        JournalEntry.reversal_of_entry_id.is_(None),
    )

    # Period activity per account.
    period_stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.posted_at >= from_dt)
        .where(JournalEntry.posted_at <= to_dt)
        .where(base_je_filter)
    )
    if division_uuid is not None:
        period_stmt = period_stmt.where(JournalLine.division_id == division_uuid)
    period_stmt = period_stmt.group_by(JournalLine.account_id)
    period_rows = list((await session.execute(period_stmt)).all())
    period_sums: dict[uuid.UUID, tuple[Decimal, Decimal]] = {
        row[0]: (Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0))) for row in period_rows
    }

    # Opening activity per account (entries strictly before period_start).
    opening_stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.posted_at < from_dt)
        .where(base_je_filter)
    )
    if division_uuid is not None:
        opening_stmt = opening_stmt.where(JournalLine.division_id == division_uuid)
    opening_stmt = opening_stmt.group_by(JournalLine.account_id)
    opening_rows = list((await session.execute(opening_stmt)).all())
    opening_sums: dict[uuid.UUID, tuple[Decimal, Decimal]] = {
        row[0]: (Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0))) for row in opening_rows
    }

    touched_ids = set(period_sums.keys()) | set(opening_sums.keys())

    if include_zero:
        accounts_stmt = select(Account)
    else:
        accounts_stmt = select(Account).where(Account.id.in_(touched_ids or [uuid.uuid4()]))
        # ``in_`` on an empty list expands to ``WHERE false`` in some dialects but
        # not all — the sentinel UUID keeps the SQL valid and returns no rows.

    accounts = list((await session.execute(accounts_stmt)).scalars().all())
    accounts.sort(key=lambda a: a.code)

    rows: list[TrialBalanceRow] = []
    total_dr = _ZERO
    total_cr = _ZERO
    for acct in accounts:
        opening_dr, opening_cr = opening_sums.get(acct.id, (_ZERO, _ZERO))
        period_dr, period_cr = period_sums.get(acct.id, (_ZERO, _ZERO))
        actual_type = acct.type.value if hasattr(acct.type, "value") else acct.type
        opening_balance = _signed_balance(actual_type, opening_dr, opening_cr)
        closing_balance = _signed_balance(
            actual_type, opening_dr + period_dr, opening_cr + period_cr
        )
        rows.append(
            TrialBalanceRow(
                account_id=str(acct.id),
                code=acct.code,
                name=acct.name,
                type=actual_type,
                opening_balance=_q(opening_balance),
                period_debit=_q(period_dr),
                period_credit=_q(period_cr),
                closing_balance=_q(closing_balance),
            )
        )
        total_dr += period_dr
        total_cr += period_cr

    return TrialBalanceReport(
        date_from=date_from,
        date_to=date_to,
        division_id=str(division_uuid) if division_uuid is not None else None,
        include_zero=include_zero,
        rows=rows,
        total_period_debit=_q(total_dr),
        total_period_credit=_q(total_cr),
    )


def to_csv(report: TrialBalanceReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(
        ["account_code", "account_name", "opening", "period_debit", "period_credit", "closing"]
    )
    for r in report.rows:
        w.writerow(
            [
                r.code,
                r.name,
                str(r.opening_balance),
                str(r.period_debit),
                str(r.period_credit),
                str(r.closing_balance),
            ]
        )
    w.writerow(
        [
            "GRAND TOTAL",
            "",
            "",
            str(report.total_period_debit),
            str(report.total_period_credit),
            "",
        ]
    )
    return buf.getvalue()


__all__ = [
    "TrialBalanceReport",
    "TrialBalanceRow",
    "build",
    "to_csv",
]
