"""Control Center aggregate service (Phase 11.4, #196).

Single endpoint feeding the admin "things that need attention"
dashboard. Each section is a cheap COUNT + a TOP-N sample ordered by
``updated_at DESC``. Empty install renders zeros.

Sections that don't yet have an authoritative source (worker run
state, websocket health) are surfaced with safe placeholders so the
frontend can render the card today and the contract doesn't shift
when the data source lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.bill import Bill, BillState
from app.models.invoice import Invoice, InvoiceState
from app.models.webhook import WebhookDelivery, WebhookDeliveryStatus
from app.services import inventory_alerts as low_stock_service

SAMPLE_LIMIT: int = 5


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class Section:
    count: int = 0
    sample: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AmountSection(Section):
    amount_total: Decimal = Decimal("0")


@dataclass
class WsHealth:
    moonraker_ws_connected: bool
    last_event_at: datetime | None


@dataclass
class ControlCenter:
    as_of: datetime
    pending_approvals: Section
    low_stock_alerts: Section
    overdue_invoices: AmountSection
    overdue_bills: AmountSection
    failed_jobs: Section
    webhook_dlq: Section
    ws_health: WsHealth


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


async def _pending_approvals(session: AsyncSession) -> Section:
    count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ApprovalRequest)
                .where(ApprovalRequest.state == ApprovalState.PENDING)
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.state == ApprovalState.PENDING)
            .order_by(ApprovalRequest.updated_at.desc())
            .limit(SAMPLE_LIMIT)
        )
    ).scalars().all()
    sample = [
        {
            "id": str(r.id),
            "subject_kind": r.subject_kind,
            "subject_id": str(r.subject_id) if r.subject_id else None,
            "requested_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return Section(count=count, sample=sample)


async def _low_stock(session: AsyncSession) -> Section:
    rows = await low_stock_service.list_low_stock(session=session)
    sample = [
        {
            "entity_kind": r.entity_kind,
            "entity_id": str(r.entity_id),
            "entity_name": r.entity_name,
            "on_hand": str(r.total_on_hand),
            "threshold": str(r.threshold),
        }
        for r in rows[:SAMPLE_LIMIT]
    ]
    return Section(count=len(rows), sample=sample)


async def _overdue_invoices(session: AsyncSession) -> AmountSection:
    count_q = (
        select(func.count(), func.coalesce(func.sum(Invoice.amount_outstanding), 0))
        .select_from(Invoice)
        .where(Invoice.state == InvoiceState.OVERDUE)
    )
    count, total = (await session.execute(count_q)).one()
    rows = (
        await session.execute(
            select(Invoice)
            .where(Invoice.state == InvoiceState.OVERDUE)
            .order_by(Invoice.updated_at.desc())
            .limit(SAMPLE_LIMIT)
        )
    ).scalars().all()
    sample = [
        {
            "id": str(r.id),
            "invoice_number": r.invoice_number,
            "amount_outstanding": str(r.amount_outstanding),
        }
        for r in rows
    ]
    return AmountSection(
        count=int(count or 0),
        amount_total=Decimal(str(total or 0)),
        sample=sample,
    )


async def _overdue_bills(session: AsyncSession) -> AmountSection:
    count_q = (
        select(func.count(), func.coalesce(func.sum(Bill.amount_outstanding), 0))
        .select_from(Bill)
        .where(Bill.state == BillState.OVERDUE)
    )
    count, total = (await session.execute(count_q)).one()
    rows = (
        await session.execute(
            select(Bill)
            .where(Bill.state == BillState.OVERDUE)
            .order_by(Bill.updated_at.desc())
            .limit(SAMPLE_LIMIT)
        )
    ).scalars().all()
    sample = [
        {
            "id": str(r.id),
            "bill_number": r.bill_number,
            "amount_outstanding": str(r.amount_outstanding),
        }
        for r in rows
    ]
    return AmountSection(
        count=int(count or 0),
        amount_total=Decimal(str(total or 0)),
        sample=sample,
    )


async def _failed_jobs(_session: AsyncSession) -> Section:
    # Worker run-state table doesn't exist yet; intentionally stub so
    # the frontend contract is stable. When the run-state table lands,
    # swap this for a real query (last_status='failed' in 24h).
    return Section(count=0, sample=[])


async def _webhook_dlq(session: AsyncSession) -> Section:
    count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(WebhookDelivery)
                .where(WebhookDelivery.last_status == WebhookDeliveryStatus.DEAD_LETTER)
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.last_status == WebhookDeliveryStatus.DEAD_LETTER)
            .order_by(WebhookDelivery.updated_at.desc())
            .limit(SAMPLE_LIMIT)
        )
    ).scalars().all()
    sample = [
        {
            "id": str(r.id),
            "subscription_id": str(r.subscription_id),
            "event_type": r.event_type,
            "attempt_count": r.attempt_count,
            "last_response_code": r.last_response_code,
        }
        for r in rows
    ]
    return Section(count=count, sample=sample)


def _ws_health() -> WsHealth:
    # No live Moonraker WS connector lives in-process today; the
    # printer monitor service polls HTTP. Surface "not connected" so
    # the contract is honest until the WS layer lands.
    return WsHealth(moonraker_ws_connected=False, last_event_at=None)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


async def build(session: AsyncSession) -> ControlCenter:
    return ControlCenter(
        as_of=datetime.now(UTC),
        pending_approvals=await _pending_approvals(session),
        low_stock_alerts=await _low_stock(session),
        overdue_invoices=await _overdue_invoices(session),
        overdue_bills=await _overdue_bills(session),
        failed_jobs=await _failed_jobs(session),
        webhook_dlq=await _webhook_dlq(session),
        ws_health=_ws_health(),
    )


__all__ = [
    "AmountSection",
    "ControlCenter",
    "SAMPLE_LIMIT",
    "Section",
    "WsHealth",
    "build",
]
