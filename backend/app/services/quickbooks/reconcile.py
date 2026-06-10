"""QBO completeness / reconciliation report + decommission gate (#317, Phase 4b).

After Phase 3, QBO is the system of record and there is no parallel local GL to
reconcile against. "Reconciliation" here means **QBO completeness + sync health**:
prove that every finalized operational record that should have produced a QBO
document actually has one, the outbox is drained, and no dead-letter or CDC drift
remains. That conjunction is the **decommission-ready** signal Phase 5 checks
before removing the local GL.

Gap detection (epic decision: *outbox coverage*): a "gap" is a finalized record
whose id has no ``synced`` row in ``qbo_sync_outbox`` for its kind. Amount
mismatches are *CDC-sourced* (decision): an externally-updated synced entity
shows up as open drift — counted here as a mismatch candidate — rather than read
back doc-by-doc from QBO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill, BillState
from app.models.bill_payment import BillPayment, BillPaymentState
from app.models.credit_note import CreditNote, CreditNoteState, DebitNote, DebitNoteState
from app.models.deposit_slip import DepositSlip, DepositSlipState
from app.models.depreciation_schedule import DepreciationEntryState, DepreciationScheduleEntry
from app.models.expense_claim import ExpenseClaim, ExpenseClaimState
from app.models.fixed_asset import FixedAsset
from app.models.fixed_asset_disposal import FixedAssetDisposal
from app.models.invoice import Invoice, InvoiceState
from app.models.payment import Payment, PaymentState
from app.models.qbo_cdc_drift import QboCdcDrift, QboDriftStatus
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.models.sale import Sale, SaleState
from app.models.settlement import Settlement, SettlementState
from app.models.tax_remittance import TaxRemittance, TaxRemittanceState
from app.services.quickbooks import outbox


@dataclass(frozen=True)
class _GapSource:
    """One outbox ``kind`` and the finalized operational records that must have
    produced a synced QBO document for it."""

    kind: str
    model: type
    ts_attr: str  # timestamp column used for the reconciliation date range
    ref_attr: str | None  # human reference (number); None → fall back to id
    states: tuple[str, ...] | None  # finalized state values; None → all rows


# The 14 gated posting sites (Phase 3b-3d). A record in a finalized state below,
# created/issued within the range, must have a ``synced`` outbox row for ``kind``.
_GAP_SOURCES: tuple[_GapSource, ...] = (
    _GapSource("sale", Sale, "created_at", "sale_number", (SaleState.FULFILLED.value,)),
    _GapSource(
        "invoice",
        Invoice,
        "issued_at",
        "invoice_number",
        (
            InvoiceState.ISSUED.value,
            InvoiceState.PARTIALLY_PAID.value,
            InvoiceState.PAID.value,
            InvoiceState.OVERDUE.value,
        ),
    ),
    _GapSource("payment", Payment, "received_at", "payment_number", (PaymentState.APPLIED.value,)),
    _GapSource(
        "bill",
        Bill,
        "issued_at",
        "bill_number",
        (
            BillState.ISSUED.value,
            BillState.PARTIALLY_PAID.value,
            BillState.PAID.value,
            BillState.OVERDUE.value,
        ),
    ),
    _GapSource(
        "bill_payment",
        BillPayment,
        "created_at",
        "payment_number",
        (BillPaymentState.POSTED.value,),
    ),
    _GapSource(
        "credit_note",
        CreditNote,
        "created_at",
        "credit_note_number",
        (CreditNoteState.ISSUED.value, CreditNoteState.APPLIED.value),
    ),
    _GapSource(
        "debit_note",
        DebitNote,
        "created_at",
        "debit_note_number",
        (DebitNoteState.ISSUED.value, DebitNoteState.APPLIED.value),
    ),
    _GapSource(
        "tax_remittance",
        TaxRemittance,
        "created_at",
        "remittance_number",
        (TaxRemittanceState.RECORDED.value,),
    ),
    _GapSource(
        "expense_claim",
        ExpenseClaim,
        "created_at",
        "claim_number",
        (ExpenseClaimState.APPROVED.value, ExpenseClaimState.REIMBURSED.value),
    ),
    _GapSource(
        "deposit_slip",
        DepositSlip,
        "created_at",
        "slip_number",
        (DepositSlipState.DEPOSITED.value, DepositSlipState.RECONCILED.value),
    ),
    _GapSource(
        "settlement",
        Settlement,
        "created_at",
        "settlement_number",
        (SettlementState.POSTED.value,),
    ),
    # Acquisition enqueues at creation, so every asset (any state) should have one.
    _GapSource("fixed_asset_acquisition", FixedAsset, "created_at", "asset_number", None),
    _GapSource("fixed_asset_disposal", FixedAssetDisposal, "created_at", None, None),
    _GapSource(
        "depreciation",
        DepreciationScheduleEntry,
        "created_at",
        None,
        (DepreciationEntryState.POSTED.value, DepreciationEntryState.ADJUSTED.value),
    ),
)


@dataclass(frozen=True)
class GapItem:
    kind: str
    local_id: str
    reference: str | None
    occurred_at: datetime | None


@dataclass(frozen=True)
class DriftItem:
    entity_type: str
    qbo_id: str
    change_type: str
    local_kind: str | None
    local_id: str | None
    occurrences: int
    last_detected_at: datetime


@dataclass(frozen=True)
class ReconciliationReport:
    date_from: date
    date_to: date
    outbox: dict[str, int]  # pending/synced/failed/dead/total (global backlog)
    gaps: list[GapItem] = field(default_factory=list)
    gap_count: int = 0
    drift: list[DriftItem] = field(default_factory=list)
    drift_open: int = 0
    mismatch_candidates: int = 0  # CDC-sourced: open drift rows of change_type "updated"
    decommission_ready: bool = False


def _range_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(date_from, datetime.min.time(), tzinfo=UTC),
        datetime.combine(date_to, datetime.max.time(), tzinfo=UTC),
    )


async def _gaps_for(
    session: AsyncSession, src: _GapSource, from_dt: datetime, to_dt: datetime
) -> list[GapItem]:
    ts_col = getattr(src.model, src.ts_attr)
    ref_col = getattr(src.model, src.ref_attr) if src.ref_attr else None

    synced = (
        select(QboSyncOutbox.local_id)
        .where(QboSyncOutbox.kind == src.kind)
        .where(QboSyncOutbox.status == QboSyncStatus.SYNCED.value)
    )
    cols: list[Any] = [src.model.id, ts_col]
    if ref_col is not None:
        cols.append(ref_col)
    stmt = select(*cols).where(ts_col >= from_dt).where(ts_col <= to_dt)
    if src.states is not None:
        stmt = stmt.where(src.model.state.in_(src.states))
    stmt = stmt.where(src.model.id.not_in(synced))

    rows = (await session.execute(stmt)).all()
    gaps: list[GapItem] = []
    for row in rows:
        ref = row[2] if ref_col is not None else None
        gaps.append(
            GapItem(
                kind=src.kind,
                local_id=str(row[0]),
                reference=str(ref) if ref is not None else None,
                occurred_at=row[1],
            )
        )
    return gaps


async def _open_drift(session: AsyncSession) -> list[DriftItem]:
    rows = (
        (
            await session.execute(
                select(QboCdcDrift)
                .where(QboCdcDrift.status == QboDriftStatus.OPEN.value)
                .order_by(QboCdcDrift.last_detected_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        DriftItem(
            entity_type=r.entity_type,
            qbo_id=r.qbo_id,
            change_type=r.change_type,
            local_kind=r.local_kind,
            local_id=str(r.local_id) if r.local_id else None,
            occurrences=r.occurrences,
            last_detected_at=r.last_detected_at,
        )
        for r in rows
    ]


async def build(session: AsyncSession, *, date_from: date, date_to: date) -> ReconciliationReport:
    """Build the completeness/reconciliation report over a date range.

    ``decommission_ready`` is True only when the outbox carries no
    ``pending``/``failed``/``dead`` rows, there are zero gaps in the range, and
    no open CDC drift — the explicit go/no-go gate for Phase 5."""
    outbox_counts = await outbox.stats(session)
    from_dt, to_dt = _range_bounds(date_from, date_to)

    gaps: list[GapItem] = []
    for src in _GAP_SOURCES:
        gaps.extend(await _gaps_for(session, src, from_dt, to_dt))

    drift = await _open_drift(session)
    mismatch_candidates = sum(1 for d in drift if d.change_type == "updated")

    backlog_clear = (
        outbox_counts.get("pending", 0) == 0
        and outbox_counts.get("failed", 0) == 0
        and outbox_counts.get("dead", 0) == 0
    )
    decommission_ready = backlog_clear and not gaps and not drift

    return ReconciliationReport(
        date_from=date_from,
        date_to=date_to,
        outbox=outbox_counts,
        gaps=gaps,
        gap_count=len(gaps),
        drift=drift,
        drift_open=len(drift),
        mismatch_candidates=mismatch_candidates,
        decommission_ready=decommission_ready,
    )
