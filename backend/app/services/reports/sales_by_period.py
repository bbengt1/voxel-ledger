"""Sales-by-period report (Phase 10.5, #180).

Buckets ``sale`` and ``refund`` rows by (``channel_id``, period bucket)
and rolls up gross / refunds / net / order-count per row.

Bucketing
---------
Done in Python after fetching raw ``(occurred_at, channel_id,
total_amount)`` rows. Avoiding ``DATE_TRUNC`` keeps the service
cross-dialect (SQLite has no native equivalent).

Supported buckets: ``day``, ``week``, ``month``, ``quarter``, ``year``.

State filtering
---------------
* Sales: ``state IN (confirmed, fulfilled)`` — drafts and cancelled
  sales never count.
* Refunds: ``state IN (approved, posted)`` — rejected / cancelled
  refunds drop out; pending refunds are tentative and excluded.

Refund attribution
------------------
A refund's contribution to the report uses the refund's own
``created_at`` for bucketing. (An alternative reading from the issue
would attribute the refund back to the sale's bucket; we picked the
simpler interpretation, which matches what a typical "Sales by
period" report shows.)
"""

from __future__ import annotations

import io
import uuid
from csv import writer as csv_writer
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refund import Refund, RefundState
from app.models.sale import Sale, SaleState

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")

Bucket = Literal["day", "week", "month", "quarter", "year"]
_BUCKETS: tuple[Bucket, ...] = ("day", "week", "month", "quarter", "year")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _bucket_start(d: date, bucket: Bucket) -> date:
    if bucket == "day":
        return d
    if bucket == "week":
        return d - timedelta(days=d.weekday())
    if bucket == "month":
        return date(d.year, d.month, 1)
    if bucket == "quarter":
        q_month = ((d.month - 1) // 3) * 3 + 1
        return date(d.year, q_month, 1)
    if bucket == "year":
        return date(d.year, 1, 1)
    raise ValueError(f"unknown bucket: {bucket!r}")


@dataclass(frozen=True)
class SalesByPeriodRow:
    channel_id: str
    bucket_start: date
    gross_sales: Decimal
    refunds: Decimal
    net_sales: Decimal
    order_count: int


@dataclass(frozen=True)
class SalesByPeriodReport:
    date_from: date
    date_to: date
    bucket: Bucket
    channel_id: str | None
    rows: list[SalesByPeriodRow]
    total_gross: Decimal
    total_refunds: Decimal
    total_net: Decimal
    total_orders: int


async def build(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    bucket: Bucket = "month",
    channel_id: uuid.UUID | str | None = None,
) -> SalesByPeriodReport:
    if bucket not in _BUCKETS:
        raise ValueError(f"unknown bucket {bucket!r}; expected one of {_BUCKETS}")
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")

    from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)

    channel_uuid: uuid.UUID | None = None
    if channel_id is not None:
        channel_uuid = (
            channel_id if isinstance(channel_id, uuid.UUID) else uuid.UUID(str(channel_id))
        )

    # --- Sales ---
    sales_stmt = (
        select(Sale.channel_id, Sale.occurred_at, Sale.total_amount)
        .where(Sale.state.in_([SaleState.CONFIRMED, SaleState.FULFILLED]))
        .where(Sale.occurred_at >= from_dt)
        .where(Sale.occurred_at <= to_dt)
    )
    if channel_uuid is not None:
        sales_stmt = sales_stmt.where(Sale.channel_id == channel_uuid)
    sales_rows = list((await session.execute(sales_stmt)).all())

    # --- Refunds ---
    refunds_stmt = (
        select(Sale.channel_id, Refund.created_at, Refund.total_amount)
        .join(Sale, Sale.id == Refund.sale_id)
        .where(Refund.state.in_([RefundState.APPROVED, RefundState.POSTED]))
        .where(Refund.created_at >= from_dt)
        .where(Refund.created_at <= to_dt)
    )
    if channel_uuid is not None:
        refunds_stmt = refunds_stmt.where(Sale.channel_id == channel_uuid)
    refund_rows = list((await session.execute(refunds_stmt)).all())

    # Bucket in Python.
    buckets: dict[tuple[uuid.UUID, date], dict[str, object]] = {}

    def _slot(chan_id: uuid.UUID, dt: datetime) -> dict[str, object]:
        key = (chan_id, _bucket_start(dt.astimezone(UTC).date(), bucket))
        slot = buckets.get(key)
        if slot is None:
            slot = {
                "gross": _ZERO,
                "refunds": _ZERO,
                "orders": 0,
            }
            buckets[key] = slot
        return slot

    for chan_id, occurred_at, total_amount in sales_rows:
        slot = _slot(chan_id, occurred_at)
        slot["gross"] = slot["gross"] + Decimal(str(total_amount))  # type: ignore[operator]
        slot["orders"] = int(slot["orders"]) + 1  # type: ignore[arg-type]

    for chan_id, created_at, total_amount in refund_rows:
        slot = _slot(chan_id, created_at)
        slot["refunds"] = slot["refunds"] + Decimal(str(total_amount))  # type: ignore[operator]

    rows: list[SalesByPeriodRow] = []
    total_gross = _ZERO
    total_refunds = _ZERO
    total_orders = 0
    for (chan_id, bucket_start), slot in sorted(
        buckets.items(), key=lambda kv: (kv[0][1], str(kv[0][0]))
    ):
        gross = _q(slot["gross"])  # type: ignore[arg-type]
        refunds = _q(slot["refunds"])  # type: ignore[arg-type]
        orders = int(slot["orders"])  # type: ignore[arg-type]
        net = _q(gross - refunds)
        rows.append(
            SalesByPeriodRow(
                channel_id=str(chan_id),
                bucket_start=bucket_start,
                gross_sales=gross,
                refunds=refunds,
                net_sales=net,
                order_count=orders,
            )
        )
        total_gross += gross
        total_refunds += refunds
        total_orders += orders

    return SalesByPeriodReport(
        date_from=date_from,
        date_to=date_to,
        bucket=bucket,
        channel_id=str(channel_uuid) if channel_uuid is not None else None,
        rows=rows,
        total_gross=_q(total_gross),
        total_refunds=_q(total_refunds),
        total_net=_q(total_gross - total_refunds),
        total_orders=total_orders,
    )


def to_csv(report: SalesByPeriodReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(["channel_id", "bucket_start", "gross_sales", "refunds", "net_sales", "order_count"])
    for r in report.rows:
        w.writerow(
            [
                r.channel_id,
                r.bucket_start.isoformat(),
                str(r.gross_sales),
                str(r.refunds),
                str(r.net_sales),
                r.order_count,
            ]
        )
    w.writerow(
        [
            "GRAND TOTAL",
            "",
            str(report.total_gross),
            str(report.total_refunds),
            str(report.total_net),
            report.total_orders,
        ]
    )
    return buf.getvalue()


__all__ = [
    "Bucket",
    "SalesByPeriodReport",
    "SalesByPeriodRow",
    "build",
    "to_csv",
]
