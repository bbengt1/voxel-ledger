"""AP aging report (Phase 8.4, #131).

Bucketed open-payable view of vendors + bills. The default buckets are
``[0-30, 31-60, 61-90, 91+]`` (cut points ``[30, 60, 90]``) with the
operator-configured ``ap.aging_bucket_days`` setting as the fallback when
no per-request override is supplied.

Mirror of :mod:`app.services.reports.ar_aging` — see that module's
docstring for the design rationale. Pure read service: pulls outstanding
bills (state in ``issued / partially_paid / overdue``), groups by vendor,
distributes ``amount_outstanding`` across buckets by days-past-due, and
returns an ``AgingReport`` for the router (which also handles CSV
serialization).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from csv import writer as csv_writer
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill, BillState
from app.models.vendor import Vendor
from app.services.settings.service import SettingsService

_ZERO = Decimal("0")

_OUTSTANDING_STATES = (
    BillState.ISSUED,
    BillState.PARTIALLY_PAID,
    BillState.OVERDUE,
)


@dataclass(frozen=True)
class AgingBucket:
    label: str
    amount: Decimal


@dataclass(frozen=True)
class AgingRow:
    vendor_id: str
    vendor_number: str
    display_name: str
    total_outstanding: Decimal
    buckets: list[AgingBucket]


@dataclass(frozen=True)
class AgingReport:
    as_of: datetime
    bucket_labels: list[str]
    rows: list[AgingRow]
    grand_total: Decimal
    grand_total_by_bucket: list[Decimal] = field(default_factory=list)


def _normalize_cut_points(cuts: Sequence[int]) -> list[int]:
    out = sorted({int(c) for c in cuts if int(c) > 0})
    if not out:
        return [30, 60, 90]
    return out


def _bucket_labels(cuts: list[int]) -> list[str]:
    labels: list[str] = []
    prev = 0
    for c in cuts:
        labels.append(f"{prev}-{c}")
        prev = c + 1
    labels.append(f"{prev}+")
    return labels


def _bucket_index(days_past_due: int, cuts: list[int]) -> int:
    for i, c in enumerate(cuts):
        if days_past_due <= c:
            return i
    return len(cuts)


async def _resolve_bucket_days(session: AsyncSession, override: Sequence[int] | None) -> list[int]:
    if override is not None:
        return _normalize_cut_points(override)
    raw = await SettingsService.get("ap.aging_bucket_days", session=session)
    if raw is None or not isinstance(raw, list):
        return [30, 60, 90]
    return _normalize_cut_points(raw)


async def build(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    buckets: Sequence[int] | None = None,
) -> AgingReport:
    now = now or datetime.now(UTC)
    cuts = await _resolve_bucket_days(session, buckets)
    labels = _bucket_labels(cuts)

    # Pull all open bills joined with their vendor.
    stmt = (
        select(Bill, Vendor)
        .join(Vendor, Vendor.id == Bill.vendor_id)
        .where(Bill.state.in_(_OUTSTANDING_STATES))
        .where(Bill.amount_outstanding > _ZERO)
        .order_by(Vendor.vendor_number.asc(), Bill.due_at.asc())
    )
    raw_rows = (await session.execute(stmt)).all()

    by_vendor: dict[str, dict[str, object]] = {}
    bucket_count = len(labels)
    for bill, vendor in raw_rows:
        vendor_id = str(vendor.id)
        entry = by_vendor.setdefault(
            vendor_id,
            {
                "vendor_number": vendor.vendor_number,
                "display_name": vendor.display_name,
                "total": _ZERO,
                "buckets": [_ZERO] * bucket_count,
            },
        )
        if bill.due_at is None:
            days_past = 0
        else:
            due = bill.due_at
            if due.tzinfo is None:
                due = due.replace(tzinfo=UTC)
            days_past = max((now - due).days, 0)
        idx = _bucket_index(days_past, cuts)
        amount = Decimal(bill.amount_outstanding)
        entry["buckets"][idx] += amount  # type: ignore[operator]
        entry["total"] = entry["total"] + amount  # type: ignore[operator]

    rows: list[AgingRow] = []
    grand_total = _ZERO
    grand_by_bucket = [_ZERO] * bucket_count
    for vendor_id, entry in by_vendor.items():
        buckets_list: list[Decimal] = entry["buckets"]  # type: ignore[assignment]
        total: Decimal = entry["total"]  # type: ignore[assignment]
        grand_total += total
        for i, val in enumerate(buckets_list):
            grand_by_bucket[i] += val
        rows.append(
            AgingRow(
                vendor_id=vendor_id,
                vendor_number=str(entry["vendor_number"]),
                display_name=str(entry["display_name"]),
                total_outstanding=total,
                buckets=[
                    AgingBucket(label=labels[i], amount=val) for i, val in enumerate(buckets_list)
                ],
            )
        )
    rows.sort(key=lambda r: r.vendor_number)

    return AgingReport(
        as_of=now,
        bucket_labels=labels,
        rows=rows,
        grand_total=grand_total,
        grand_total_by_bucket=grand_by_bucket,
    )


def to_csv(report: AgingReport) -> str:
    """Serialize an :class:`AgingReport` to CSV (string).

    Header row: ``vendor_number,display_name,<bucket-labels>,total``.
    A trailing ``GRAND TOTAL`` row carries the per-bucket and total sums.
    """
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(["vendor_number", "display_name", *report.bucket_labels, "total_outstanding"])
    for row in report.rows:
        w.writerow(
            [
                row.vendor_number,
                row.display_name,
                *(str(b.amount) for b in row.buckets),
                str(row.total_outstanding),
            ]
        )
    w.writerow(
        [
            "GRAND TOTAL",
            "",
            *(str(v) for v in report.grand_total_by_bucket),
            str(report.grand_total),
        ]
    )
    return buf.getvalue()


__all__ = [
    "AgingBucket",
    "AgingReport",
    "AgingRow",
    "build",
    "to_csv",
]
