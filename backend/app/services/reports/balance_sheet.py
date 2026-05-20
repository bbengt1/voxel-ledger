"""Balance Sheet report (Phase 10.2, #177).

Point-in-time balances for every account with
``type IN (asset, liability, equity)``, computed from journal lines
joined to entries with ``posted_at <= as_of``.

Sign convention
---------------
* assets:      balance = sum(debit) - sum(credit)  (normal Dr)
* liabilities: balance = sum(credit) - sum(debit)  (normal Cr)
* equity:      balance = sum(credit) - sum(debit)  (normal Cr)

Reversal pairs are filtered out (both the ``is_reversed=true`` original
and the reversal entry drop), matching the income-statement service.

Retained-earnings rollup
------------------------
When ``reports.retained_earnings_account_id`` is set, the report adds
the current-year net income (revenue - expense from Jan 1 through
``as_of``) onto that equity account's balance. This keeps the report
balanced before the operator manually closes P&L to retained earnings.

The report always exposes the residual
``total_assets - (total_liabilities + total_equity)`` so the operator
can see when it's out of balance.
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

_BALANCE_TYPES: tuple[str, ...] = (
    AccountType.ASSET.value,
    AccountType.LIABILITY.value,
    AccountType.EQUITY.value,
)
_PNL_TYPES: tuple[str, ...] = (
    AccountType.REVENUE.value,
    AccountType.EXPENSE.value,
)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class BalanceSheetRow:
    account_id: str
    code: str
    name: str
    depth: int
    section: str  # "asset" | "liability" | "equity"
    balance: Decimal


@dataclass(frozen=True)
class BalanceSheetReport:
    as_of: date
    division_id: str | None
    asset_rows: list[BalanceSheetRow]
    liability_rows: list[BalanceSheetRow]
    equity_rows: list[BalanceSheetRow]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    total_liabilities_and_equity: Decimal
    imbalance: Decimal  # total_assets - (total_liabilities + total_equity)


def _depth(account: Account, by_id: dict[uuid.UUID, Account]) -> int:
    depth = 0
    current = account
    seen: set[uuid.UUID] = set()
    while current.parent_account_id is not None:
        if current.parent_account_id in seen:
            break
        seen.add(current.parent_account_id)
        parent = by_id.get(current.parent_account_id)
        if parent is None:
            break
        depth += 1
        current = parent
    return depth


async def _resolve_retained_earnings_account_id(
    session: AsyncSession,
) -> uuid.UUID | None:
    raw = await SettingsService.get("reports.retained_earnings_account_id", session=session)
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


async def build(
    session: AsyncSession,
    *,
    as_of: date,
    division_id: uuid.UUID | str | None = None,
) -> BalanceSheetReport:
    as_of_dt = datetime.combine(as_of, datetime.max.time(), tzinfo=UTC)

    division_uuid: uuid.UUID | None = None
    if division_id is not None:
        division_uuid = (
            division_id if isinstance(division_id, uuid.UUID) else uuid.UUID(str(division_id))
        )

    retained_earnings_id = await _resolve_retained_earnings_account_id(session)

    # Pre-load balance-sheet accounts plus any parents missing from that set.
    accounts_stmt = select(Account).where(Account.type.in_(list(_BALANCE_TYPES)))
    accounts = list((await session.execute(accounts_stmt)).scalars().all())
    accounts_by_id = {a.id: a for a in accounts}
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

    # Single aggregation over the balance-sheet accounts.
    je_filter = and_(
        JournalEntry.posted_at <= as_of_dt,
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
        .join(Account, Account.id == JournalLine.account_id)
        .where(Account.type.in_(list(_BALANCE_TYPES)))
        .where(je_filter)
    )
    if division_uuid is not None:
        sums_stmt = sums_stmt.where(JournalLine.division_id == division_uuid)
    sums_stmt = sums_stmt.group_by(JournalLine.account_id)

    sums_rows = list((await session.execute(sums_stmt)).all())
    sums_by_account: dict[uuid.UUID, tuple[Decimal, Decimal]] = {
        row[0]: (Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0))) for row in sums_rows
    }

    # Retained-earnings rollup: net income (revenue - expense) from Jan 1
    # of the as_of year through ``as_of``. Same reversal filter.
    re_amount = _ZERO
    if retained_earnings_id is not None:
        year_start = datetime(as_of.year, 1, 1, tzinfo=UTC)
        ni_stmt = (
            select(
                Account.type,
                func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
                func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
            )
            .select_from(JournalLine)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .where(Account.type.in_(list(_PNL_TYPES)))
            .where(
                and_(
                    JournalEntry.posted_at >= year_start,
                    JournalEntry.posted_at <= as_of_dt,
                    JournalEntry.is_reversed.is_(False),
                    JournalEntry.reversal_of_entry_id.is_(None),
                )
            )
            .group_by(Account.type)
        )
        if division_uuid is not None:
            ni_stmt = ni_stmt.where(JournalLine.division_id == division_uuid)
        for row_type, dr, cr in (await session.execute(ni_stmt)).all():
            actual = row_type.value if hasattr(row_type, "value") else row_type
            d = Decimal(str(dr or 0))
            c = Decimal(str(cr or 0))
            if actual == AccountType.REVENUE.value:
                re_amount += c - d
            else:  # expense
                re_amount -= d - c

    asset_rows: list[BalanceSheetRow] = []
    liability_rows: list[BalanceSheetRow] = []
    equity_rows: list[BalanceSheetRow] = []

    for account in accounts:
        dr, cr = sums_by_account.get(account.id, (_ZERO, _ZERO))
        actual_type = account.type.value if hasattr(account.type, "value") else account.type
        depth = _depth(account, accounts_by_id)
        if actual_type == AccountType.ASSET.value:
            balance = _q(dr - cr)
            row = BalanceSheetRow(
                account_id=str(account.id),
                code=account.code,
                name=account.name,
                depth=depth,
                section="asset",
                balance=balance,
            )
            if balance != _ZERO or dr != _ZERO or cr != _ZERO:
                asset_rows.append(row)
        elif actual_type == AccountType.LIABILITY.value:
            balance = _q(cr - dr)
            row = BalanceSheetRow(
                account_id=str(account.id),
                code=account.code,
                name=account.name,
                depth=depth,
                section="liability",
                balance=balance,
            )
            if balance != _ZERO or dr != _ZERO or cr != _ZERO:
                liability_rows.append(row)
        else:  # equity
            balance = _q(cr - dr)
            if retained_earnings_id is not None and account.id == retained_earnings_id:
                balance = _q(balance + re_amount)
            row = BalanceSheetRow(
                account_id=str(account.id),
                code=account.code,
                name=account.name,
                depth=depth,
                section="equity",
                balance=balance,
            )
            if balance != _ZERO or dr != _ZERO or cr != _ZERO:
                equity_rows.append(row)

    # If retained-earnings rollup applies but the operator hasn't posted to
    # the configured equity account yet, surface a synthetic row so the
    # current-period net income shows up under Equity.
    if (
        retained_earnings_id is not None
        and retained_earnings_id not in {uuid.UUID(r.account_id) for r in equity_rows}
        and re_amount != _ZERO
    ):
        acct = accounts_by_id.get(retained_earnings_id)
        if acct is not None:
            equity_rows.append(
                BalanceSheetRow(
                    account_id=str(acct.id),
                    code=acct.code,
                    name=acct.name,
                    depth=_depth(acct, accounts_by_id),
                    section="equity",
                    balance=_q(re_amount),
                )
            )

    asset_rows.sort(key=lambda r: r.code)
    liability_rows.sort(key=lambda r: r.code)
    equity_rows.sort(key=lambda r: r.code)

    total_assets = _q(sum((r.balance for r in asset_rows), _ZERO))
    total_liabilities = _q(sum((r.balance for r in liability_rows), _ZERO))
    total_equity = _q(sum((r.balance for r in equity_rows), _ZERO))
    total_le = _q(total_liabilities + total_equity)

    return BalanceSheetReport(
        as_of=as_of,
        division_id=str(division_uuid) if division_uuid is not None else None,
        asset_rows=asset_rows,
        liability_rows=liability_rows,
        equity_rows=equity_rows,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        total_liabilities_and_equity=total_le,
        imbalance=_q(total_assets - total_le),
    )


def to_csv(report: BalanceSheetReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(["section", "account_code", "account_name", "depth", "balance"])
    for r in report.asset_rows:
        w.writerow(["Assets", r.code, r.name, r.depth, str(r.balance)])
    w.writerow(["Assets", "TOTAL", "", "", str(report.total_assets)])
    for r in report.liability_rows:
        w.writerow(["Liabilities", r.code, r.name, r.depth, str(r.balance)])
    w.writerow(["Liabilities", "TOTAL", "", "", str(report.total_liabilities)])
    for r in report.equity_rows:
        w.writerow(["Equity", r.code, r.name, r.depth, str(r.balance)])
    w.writerow(["Equity", "TOTAL", "", "", str(report.total_equity)])
    w.writerow(
        [
            "Totals",
            "LIABILITIES + EQUITY",
            "",
            "",
            str(report.total_liabilities_and_equity),
        ]
    )
    w.writerow(["Totals", "IMBALANCE", "", "", str(report.imbalance)])
    return buf.getvalue()


__all__ = [
    "BalanceSheetReport",
    "BalanceSheetRow",
    "build",
    "to_csv",
]
