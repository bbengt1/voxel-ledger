"""General-ledger detail report (Parity #226).

The drill-down behind the trial balance. For each account (optionally
filtered to a single ``account_id``), returns:

  * ``opening_balance`` — signed balance from entries strictly
    before ``date_from``.
  * Per-line activity within the window, in chronological order:
    JE id, entry number, posted_at, description, debit, credit,
    running_balance.
  * ``closing_balance`` — opening plus period activity.

Mirrors the sign convention from :mod:`app.services.reports.trial_balance`:
asset / expense are Dr-normal; liability / equity / revenue are
Cr-normal. The running balance updates by ``+debit - credit`` for
Dr-normal accounts and ``+credit - debit`` for Cr-normal accounts —
that's what an operator scanning the report expects.

Reversed JEs and reversal-pair entries are filtered out (matches
the rest of the financial-report stack).
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


def _signed_delta(account_type: str, debit: Decimal, credit: Decimal) -> Decimal:
    """Signed contribution to the running balance for one line."""
    if account_type in _DR_NORMAL:
        return debit - credit
    return credit - debit


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerLine:
    journal_entry_id: str
    entry_number: str
    posted_at: datetime
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


@dataclass(frozen=True)
class LedgerSection:
    account_id: str
    code: str
    name: str
    type: str
    opening_balance: Decimal
    closing_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    lines: list[LedgerLine]


@dataclass(frozen=True)
class LedgerDetailReport:
    date_from: date
    date_to: date
    account_id: str | None
    division_id: str | None
    sections: list[LedgerSection]


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    account_id: uuid.UUID | str | None = None,
    division_id: uuid.UUID | str | None = None,
) -> LedgerDetailReport:
    """Return a per-account section list ordered by account code.

    When ``account_id`` is set, only that account's section is
    returned. When ``division_id`` is set, only lines tagged with
    that division contribute to both opening and period activity.
    """
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    account_uuid: uuid.UUID | None = None
    if account_id is not None:
        account_uuid = (
            account_id if isinstance(account_id, uuid.UUID) else uuid.UUID(str(account_id))
        )
    division_uuid: uuid.UUID | None = None
    if division_id is not None:
        division_uuid = (
            division_id if isinstance(division_id, uuid.UUID) else uuid.UUID(str(division_id))
        )

    base_je_filter = and_(
        JournalEntry.is_reversed.is_(False),
        JournalEntry.reversal_of_entry_id.is_(None),
    )

    # 1. Opening balance per account (entries strictly before date_from).
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
    if account_uuid is not None:
        opening_stmt = opening_stmt.where(JournalLine.account_id == account_uuid)
    if division_uuid is not None:
        opening_stmt = opening_stmt.where(JournalLine.division_id == division_uuid)
    opening_stmt = opening_stmt.group_by(JournalLine.account_id)
    opening_sums: dict[uuid.UUID, tuple[Decimal, Decimal]] = {
        row[0]: (Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0)))
        for row in (await session.execute(opening_stmt)).all()
    }

    # 2. Period lines, joined to journal_entry for posted_at + description +
    # entry_number, ordered by (posted_at, entry_id, line_number) so the
    # running balance is deterministic.
    lines_stmt = (
        select(
            JournalLine.account_id,
            JournalEntry.id,
            JournalEntry.entry_number,
            JournalEntry.posted_at,
            JournalEntry.description,
            JournalLine.debit,
            JournalLine.credit,
            JournalLine.line_number,
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.posted_at >= from_dt)
        .where(JournalEntry.posted_at <= to_dt)
        .where(base_je_filter)
    )
    if account_uuid is not None:
        lines_stmt = lines_stmt.where(JournalLine.account_id == account_uuid)
    if division_uuid is not None:
        lines_stmt = lines_stmt.where(JournalLine.division_id == division_uuid)
    lines_stmt = lines_stmt.order_by(
        JournalEntry.posted_at.asc(),
        JournalEntry.id.asc(),
        JournalLine.line_number.asc(),
    )
    line_rows = list((await session.execute(lines_stmt)).all())

    touched_ids = (
        {row[0] for row in line_rows}
        | set(opening_sums.keys())
        | ({account_uuid} if account_uuid is not None else set())
    )

    # 3. Account metadata for every touched account (or just the
    # filtered one).
    if account_uuid is not None:
        accounts_stmt = select(Account).where(Account.id == account_uuid)
    elif touched_ids:
        accounts_stmt = select(Account).where(Account.id.in_(touched_ids))
    else:
        return LedgerDetailReport(
            date_from=date_from,
            date_to=date_to,
            account_id=None,
            division_id=str(division_uuid) if division_uuid else None,
            sections=[],
        )
    accounts = list((await session.execute(accounts_stmt)).scalars().all())
    accounts.sort(key=lambda a: a.code)

    # 4. Bucket lines by account.
    lines_by_account: dict[uuid.UUID, list[tuple]] = {a.id: [] for a in accounts}
    for row in line_rows:
        bucket = lines_by_account.setdefault(row[0], [])
        bucket.append(row)

    sections: list[LedgerSection] = []
    for acct in accounts:
        actual_type = acct.type.value if hasattr(acct.type, "value") else acct.type
        opening_dr, opening_cr = opening_sums.get(acct.id, (_ZERO, _ZERO))
        opening_balance = _signed_delta(actual_type, opening_dr, opening_cr)

        running = opening_balance
        period_dr = _ZERO
        period_cr = _ZERO
        rendered_lines: list[LedgerLine] = []
        for row in lines_by_account.get(acct.id, []):
            (_acct_id, je_id, entry_number, posted_at, description, dr, cr, _line_no) = row
            dr_dec = Decimal(str(dr or 0))
            cr_dec = Decimal(str(cr or 0))
            period_dr += dr_dec
            period_cr += cr_dec
            running += _signed_delta(actual_type, dr_dec, cr_dec)
            rendered_lines.append(
                LedgerLine(
                    journal_entry_id=str(je_id),
                    entry_number=entry_number,
                    posted_at=posted_at,
                    description=description,
                    debit=_q(dr_dec),
                    credit=_q(cr_dec),
                    running_balance=_q(running),
                )
            )
        closing_balance = running

        sections.append(
            LedgerSection(
                account_id=str(acct.id),
                code=acct.code,
                name=acct.name,
                type=actual_type,
                opening_balance=_q(opening_balance),
                closing_balance=_q(closing_balance),
                period_debit=_q(period_dr),
                period_credit=_q(period_cr),
                lines=rendered_lines,
            )
        )

    return LedgerDetailReport(
        date_from=date_from,
        date_to=date_to,
        account_id=str(account_uuid) if account_uuid is not None else None,
        division_id=str(division_uuid) if division_uuid is not None else None,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def to_csv(report: LedgerDetailReport) -> str:
    """One row per line plus opening/closing rows per account.

    Column shape matches what a bookkeeper would paste into Excel
    for spot-tying: ``account_code, account_name, posted_at,
    entry_number, description, debit, credit, running_balance``.
    """
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(
        [
            "account_code",
            "account_name",
            "posted_at",
            "entry_number",
            "description",
            "debit",
            "credit",
            "running_balance",
        ]
    )
    for section in report.sections:
        # Opening row (no JE).
        w.writerow(
            [
                section.code,
                section.name,
                "",
                "",
                "Opening balance",
                "",
                "",
                str(section.opening_balance),
            ]
        )
        for line in section.lines:
            w.writerow(
                [
                    section.code,
                    section.name,
                    line.posted_at.isoformat(),
                    line.entry_number,
                    line.description,
                    str(line.debit) if line.debit > 0 else "",
                    str(line.credit) if line.credit > 0 else "",
                    str(line.running_balance),
                ]
            )
        # Closing row.
        w.writerow(
            [
                section.code,
                section.name,
                "",
                "",
                "Closing balance",
                str(section.period_debit),
                str(section.period_credit),
                str(section.closing_balance),
            ]
        )
    return buf.getvalue()


__all__ = [
    "LedgerDetailReport",
    "LedgerLine",
    "LedgerSection",
    "build",
    "to_csv",
]
