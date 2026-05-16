"""AR aging report (Phase 7.6, #114).

Bucketed outstanding-AR by customer. Pure SQL against ``invoice`` +
``customer``. The ``amount_outstanding`` column on ``invoice`` is
already the source of truth — Phase 7.3 maintains it on issue, and
Phase 7.4 will reduce it on payment application. We aggregate that
column directly rather than reconstructing from payments to keep the
query single-pass.

Performance budget: < 500 ms p95 against 1k customers / 10k invoices.
The compound index ``ix_invoice_state_due_at`` (added by Phase 7.6's
migration 0036) covers the WHERE predicate. The bucket math is done
in Python after a single fetch of (customer_id, customer_number,
display_name, due_at, amount_outstanding).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceState

_ZERO = Decimal("0")


@dataclass
class AgingBucketAmount:
    label: str  # e.g. "0-30", "31-60", "61-90", "91+"
    lower: int  # inclusive day lower bound
    upper: int | None  # inclusive day upper bound (None = "+")
    amount: Decimal = _ZERO


@dataclass
class CustomerAgingRow:
    customer_id: str
    customer_number: str
    display_name: str
    total_outstanding: Decimal
    buckets: list[AgingBucketAmount]


@dataclass
class AgingReport:
    as_of: datetime
    bucket_days: list[int]
    rows: list[CustomerAgingRow] = field(default_factory=list)
    grand_total: Decimal = _ZERO
    grand_total_buckets: list[AgingBucketAmount] = field(default_factory=list)


def _make_empty_buckets(bucket_days: list[int]) -> list[AgingBucketAmount]:
    """Construct empty bucket templates from cut-points.

    ``[30, 60, 90]`` → ``[0-30, 31-60, 61-90, 91+]``.
    """
    out: list[AgingBucketAmount] = []
    lower = 0
    for upper in bucket_days:
        label = f"{lower}-{upper}" if lower > 0 else f"0-{upper}"
        out.append(AgingBucketAmount(label=label, lower=lower, upper=upper))
        lower = upper + 1
    out.append(AgingBucketAmount(label=f"{lower}+", lower=lower, upper=None))
    return out


def _bucket_for_days(buckets: list[AgingBucketAmount], days: int) -> AgingBucketAmount:
    for b in buckets:
        if b.upper is None:
            if days >= b.lower:
                return b
        elif b.lower <= days <= b.upper:
            return b
    # Fallthrough: shouldn't happen with the structure produced above,
    # but on a totally absurd input we still want a stable answer.
    return buckets[-1]


def parse_bucket_query(raw: str | None, default: list[int]) -> list[int]:
    """Parse ``?buckets=0,30,60,90,120`` into a cut-point list.

    The leading ``0`` is conventional and ignored; the remaining
    strictly-increasing positive integers are the cut-points.
    """
    if not raw:
        return list(default)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        nums = [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"invalid buckets parameter: {raw!r}") from exc
    if not nums:
        return list(default)
    # Drop a leading 0 if present so callers can write ``0,30,60,90`` or
    # ``30,60,90`` interchangeably.
    if nums[0] == 0:
        nums = nums[1:]
    if not nums:
        raise ValueError("buckets must contain at least one positive cut-point")
    for n in nums:
        if n <= 0:
            raise ValueError("bucket cut-points must be positive")
    from itertools import pairwise

    if any(b <= a for a, b in pairwise(nums)):
        raise ValueError("bucket cut-points must be strictly increasing")
    return nums


async def build_ar_aging(
    *,
    session: AsyncSession,
    as_of: datetime | None = None,
    bucket_days: list[int],
) -> AgingReport:
    """Build the AR aging report.

    Aggregates outstanding AR by customer, bucketed by days past
    ``due_at``. Invoices with ``amount_outstanding <= 0``, in ``draft``
    or ``void`` state, or with no ``due_at`` are excluded.
    """
    if as_of is None:
        as_of = datetime.now(UTC)

    # Single-pass SQL. The states list keeps draft/void out so the
    # index on (state, due_at) is the right shape.
    stmt = (
        select(
            Invoice.customer_id,
            Customer.customer_number,
            Customer.display_name,
            Invoice.due_at,
            Invoice.amount_outstanding,
        )
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(Invoice.due_at.is_not(None))
        .where(Invoice.amount_outstanding > 0)
        .where(
            Invoice.state.in_(
                [
                    InvoiceState.ISSUED,
                    InvoiceState.PARTIALLY_PAID,
                    InvoiceState.OVERDUE,
                ]
            )
        )
    )
    result = await session.execute(stmt)

    per_customer: dict[str, CustomerAgingRow] = {}

    for customer_id, customer_number, display_name, due_at, amount_outstanding in result.all():
        # SQLite drops timezone info round-tripping DateTime columns.
        # Force-align both sides so the subtraction never raises.
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        as_of_aligned = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)
        days = max(0, (as_of_aligned - due_at).days)
        key = str(customer_id)
        row = per_customer.get(key)
        if row is None:
            row = CustomerAgingRow(
                customer_id=key,
                customer_number=customer_number,
                display_name=display_name,
                total_outstanding=_ZERO,
                buckets=_make_empty_buckets(bucket_days),
            )
            per_customer[key] = row
        bucket = _bucket_for_days(row.buckets, days)
        bucket.amount += amount_outstanding
        row.total_outstanding += amount_outstanding

    grand_total_buckets = _make_empty_buckets(bucket_days)
    grand_total = _ZERO
    rows = sorted(
        per_customer.values(),
        key=lambda r: (r.display_name.lower(), r.customer_number),
    )
    for row in rows:
        grand_total += row.total_outstanding
        for src, dst in zip(row.buckets, grand_total_buckets, strict=False):
            dst.amount += src.amount

    return AgingReport(
        as_of=as_of,
        bucket_days=bucket_days,
        rows=rows,
        grand_total=grand_total,
        grand_total_buckets=grand_total_buckets,
    )


def render_csv(report: AgingReport) -> str:
    """Render the report as a CSV string."""
    import csv

    buf = io.StringIO()
    writer = csv.writer(buf)

    header = ["customer_number", "display_name", "total_outstanding"]
    bucket_template = (
        report.rows[0].buckets if report.rows else _make_empty_buckets(report.bucket_days)
    )
    header.extend(b.label for b in bucket_template)
    writer.writerow(header)

    for row in report.rows:
        out = [row.customer_number, row.display_name, str(row.total_outstanding)]
        out.extend(str(b.amount) for b in row.buckets)
        writer.writerow(out)

    # Grand total row.
    grand = ["TOTAL", "", str(report.grand_total)]
    grand.extend(str(b.amount) for b in report.grand_total_buckets)
    writer.writerow(grand)
    return buf.getvalue()
