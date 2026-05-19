"""Sales-tax liability report (Phase 9.6, #158).

Pure read query that aggregates, per ``tax_rate``:

* ``tax_collected`` — Σ credits on the rate's ``liability_account_id``
  for every journal line whose entry ``posted_at`` falls in
  ``[date_from, date_to]``. These are the Cr lines posted at invoice
  issue.
* ``tax_remitted`` — Σ debits on the same liability account in the
  same window. These are the Dr lines from posted (non-cancelled)
  ``tax_remittance`` rows.
* ``net_liability`` — ``tax_collected - tax_remitted``.
* ``gross_taxable_sales`` — best-effort: when ``rate.rate > 0`` and the
  rate is NOT compound-on-previous, ``tax_collected / rate``. For
  compound rates and zero-rate flags we report ``Decimal("0")`` and the
  caller can ignore the column. Documented in the column header.

The window is half-open closed on both ends so a Q1 report from
``2026-01-01`` to ``2026-03-31`` includes any entry posted on those
exact dates (end-of-day on the upper bound).
"""

from __future__ import annotations

import io
import uuid
from csv import writer as csv_writer
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.models.tax_profile import TaxProfile

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TaxLiabilityRow:
    profile_id: str
    profile_code: str
    profile_name: str
    jurisdiction: str
    rate_id: str
    rate_name: str
    rate: Decimal
    compound_on_previous: bool
    tax_collected: Decimal
    tax_remitted: Decimal
    net_liability: Decimal
    gross_taxable_sales: Decimal


@dataclass(frozen=True)
class TaxLiabilityReport:
    date_from: date
    date_to: date
    rows: list[TaxLiabilityRow]
    grand_total_collected: Decimal
    grand_total_remitted: Decimal
    grand_total_net: Decimal


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    profile_id: uuid.UUID | str | None = None,
) -> TaxLiabilityReport:
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    stmt = select(TaxProfile).options(selectinload(TaxProfile.rates))
    if profile_id is not None:
        pid = profile_id if isinstance(profile_id, uuid.UUID) else uuid.UUID(str(profile_id))
        stmt = stmt.where(TaxProfile.id == pid)
    stmt = stmt.order_by(TaxProfile.code.asc())
    profiles = list((await session.execute(stmt)).scalars().all())

    rows: list[TaxLiabilityRow] = []
    grand_collected = _ZERO
    grand_remitted = _ZERO
    for profile in profiles:
        for rate in sorted(profile.rates, key=lambda r: r.ordinal):
            sums_stmt = (
                select(
                    func.coalesce(func.sum(JournalLine.credit), 0),
                    func.coalesce(func.sum(JournalLine.debit), 0),
                )
                .select_from(JournalLine)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .where(JournalLine.account_id == rate.liability_account_id)
                .where(JournalEntry.posted_at >= from_dt)
                .where(JournalEntry.posted_at <= to_dt)
            )
            row = (await session.execute(sums_stmt)).one()
            collected = _q(Decimal(str(row[0] or 0)))
            remitted = _q(Decimal(str(row[1] or 0)))
            net = collected - remitted

            rate_value = Decimal(rate.rate)
            if rate_value > _ZERO and not rate.compound_on_previous:
                gross = _q(collected / rate_value)
            else:
                gross = _ZERO

            rows.append(
                TaxLiabilityRow(
                    profile_id=str(profile.id),
                    profile_code=profile.code,
                    profile_name=profile.name,
                    jurisdiction=profile.jurisdiction,
                    rate_id=str(rate.id),
                    rate_name=rate.name,
                    rate=rate_value,
                    compound_on_previous=rate.compound_on_previous,
                    tax_collected=collected,
                    tax_remitted=remitted,
                    net_liability=net,
                    gross_taxable_sales=gross,
                )
            )
            grand_collected += collected
            grand_remitted += remitted

    return TaxLiabilityReport(
        date_from=date_from,
        date_to=date_to,
        rows=rows,
        grand_total_collected=grand_collected,
        grand_total_remitted=grand_remitted,
        grand_total_net=grand_collected - grand_remitted,
    )


def to_csv(report: TaxLiabilityReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(
        [
            "profile_code",
            "profile_name",
            "jurisdiction",
            "rate_name",
            "rate",
            "compound_on_previous",
            "gross_taxable_sales",
            "tax_collected",
            "tax_remitted",
            "net_liability",
        ]
    )
    for row in report.rows:
        w.writerow(
            [
                row.profile_code,
                row.profile_name,
                row.jurisdiction,
                row.rate_name,
                str(row.rate),
                "true" if row.compound_on_previous else "false",
                str(row.gross_taxable_sales),
                str(row.tax_collected),
                str(row.tax_remitted),
                str(row.net_liability),
            ]
        )
    w.writerow(
        [
            "GRAND TOTAL",
            "",
            "",
            "",
            "",
            "",
            "",
            str(report.grand_total_collected),
            str(report.grand_total_remitted),
            str(report.grand_total_net),
        ]
    )
    return buf.getvalue()


__all__ = [
    "TaxLiabilityReport",
    "TaxLiabilityRow",
    "build",
    "to_csv",
]
