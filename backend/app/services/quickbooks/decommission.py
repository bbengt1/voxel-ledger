"""Decommission cutover readiness + declaration — the Phase-5 hard gate (#318, 5c).

Composes the three additive prerequisites into one go/no-go signal and records
the owner's explicit cutover declaration:

1. **Reconciliation clean** (Phase 4b): ``reconcile.build(...)`` reports
   ``decommission_ready`` — outbox drained, no gaps, no open drift.
2. **Balanced archive** (5a): the latest :class:`GlArchiveManifest` is balanced
   and snapshots the *same* cutover date.
3. **Opening balance in QBO** (5b): the ``opening_balance`` outbox row is
   ``synced`` and dated at the *same* cutover date.

The date-coherence checks are deliberate: a cutover where the archive, the QBO
opening balances, and the declaration disagree about "as of when" is not a
cutover, it's a discrepancy. Archives are cheap — re-run 5a/5b for the right
date instead of declaring around a mismatch.

:func:`declare_cutover` re-validates everything inside the declaring
transaction and persists a :class:`GlDecommissionCutover` row with the full
readiness snapshot as audit evidence. The destructive sub-phases (5d-5f) must
call :func:`is_cutover_declared` and refuse without it.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gl_decommission_cutover import GlDecommissionCutover
from app.models.qbo_sync_outbox import QboSyncStatus
from app.services.quickbooks import archive, opening_balance, reconcile
from app.services.quickbooks import outbox as qbo_outbox

# Reconciliation look-back used for the gate (mirrors the Phase-4b endpoint).
_RECON_RANGE_DAYS = 90


class DecommissionError(RuntimeError):
    """Base. Routers map to 400/409."""


class NotReadyError(DecommissionError):
    """One or more cutover preconditions failed; ``reasons`` lists them all."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("cutover preconditions not met: " + "; ".join(reasons))


class AlreadyDeclaredError(DecommissionError):
    """A cutover declaration already stands."""


@dataclass(frozen=True)
class DecommissionReadiness:
    cutover_date: date
    ready: bool
    reasons: list[str] = field(default_factory=list)  # empty when ready
    # Component detail (what the operator needs to fix, and the audit snapshot).
    quickbooks_enabled: bool = False
    reconciliation_ready: bool = False
    reconciliation: dict[str, Any] = field(default_factory=dict)
    archive_manifest_id: uuid.UUID | None = None
    archive_balanced: bool = False
    archive_cutover_date: date | None = None
    opening_balance_outbox_id: uuid.UUID | None = None
    opening_balance_status: str | None = None
    opening_balance_txn_date: date | None = None
    declared: bool = False


async def latest_declaration(session: AsyncSession) -> GlDecommissionCutover | None:
    return (
        (
            await session.execute(
                select(GlDecommissionCutover)
                .order_by(GlDecommissionCutover.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def is_cutover_declared(session: AsyncSession) -> bool:
    """The gate the destructive sub-phases (5d-5f) must check."""
    return await latest_declaration(session) is not None


def _parse_txn_date(payload: dict[str, Any]) -> date | None:
    raw = payload.get("txn_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


async def build_readiness(session: AsyncSession, *, cutover_date: date) -> DecommissionReadiness:
    """Evaluate every cutover precondition for ``cutover_date``."""
    reasons: list[str] = []

    enabled = await qbo_outbox.is_enabled(session)
    if not enabled:
        reasons.append("quickbooks.enabled is off")

    date_to = datetime.now(UTC).date()
    date_from = date_to - timedelta(days=_RECON_RANGE_DAYS)
    recon = await reconcile.build(session, date_from=date_from, date_to=date_to)
    if not recon.decommission_ready:
        reasons.append(
            "reconciliation gate is not clean "
            f"(gaps={recon.gap_count}, drift_open={recon.drift_open}, "
            f"outbox={recon.outbox})"
        )

    manifest = await archive.latest(session)
    if manifest is None:
        reasons.append("no GL archive exists (run Phase 5a first)")
    else:
        if not manifest.balanced:
            reasons.append(
                f"latest GL archive {manifest.id} is not balanced "
                f"(Dr {manifest.total_debits} != Cr {manifest.total_credits})"
            )
        if manifest.cutover_date != cutover_date:
            reasons.append(
                f"latest GL archive snapshots {manifest.cutover_date.isoformat()}, "
                f"not the declared cutover {cutover_date.isoformat()}; re-archive"
            )

    ob_row = await opening_balance.seed_status(session)
    ob_txn_date: date | None = None
    if ob_row is None:
        reasons.append("opening balances were never seeded to QBO (run Phase 5b first)")
    else:
        if ob_row.status != QboSyncStatus.SYNCED.value:
            reasons.append(
                f"opening-balance JE is {ob_row.status!r}, not synced " f"(outbox row {ob_row.id})"
            )
        ob_txn_date = _parse_txn_date(ob_row.payload or {})
        if ob_txn_date != cutover_date:
            reasons.append(
                "opening-balance JE is dated "
                f"{ob_txn_date.isoformat() if ob_txn_date else 'unknown'}, "
                f"not the declared cutover {cutover_date.isoformat()}"
            )

    declared = await is_cutover_declared(session)

    return DecommissionReadiness(
        cutover_date=cutover_date,
        ready=not reasons,
        reasons=reasons,
        quickbooks_enabled=enabled,
        reconciliation_ready=recon.decommission_ready,
        reconciliation={
            "date_from": recon.date_from.isoformat(),
            "date_to": recon.date_to.isoformat(),
            "outbox": recon.outbox,
            "gap_count": recon.gap_count,
            "drift_open": recon.drift_open,
            "mismatch_candidates": recon.mismatch_candidates,
        },
        archive_manifest_id=manifest.id if manifest else None,
        archive_balanced=bool(manifest and manifest.balanced),
        archive_cutover_date=manifest.cutover_date if manifest else None,
        opening_balance_outbox_id=ob_row.id if ob_row else None,
        opening_balance_status=ob_row.status if ob_row else None,
        opening_balance_txn_date=ob_txn_date,
        declared=declared,
    )


def _snapshot(readiness: DecommissionReadiness) -> dict[str, Any]:
    """JSON-safe dump of the readiness report for the audit column."""
    raw = asdict(readiness)
    for key, value in raw.items():
        if isinstance(value, date):
            raw[key] = value.isoformat()
        elif isinstance(value, uuid.UUID):
            raw[key] = str(value)
    return raw


async def declare_cutover(
    session: AsyncSession,
    *,
    cutover_date: date,
    actor_user_id: uuid.UUID | None,
) -> GlDecommissionCutover:
    """Record the owner's cutover declaration. Caller commits.

    Raises :class:`AlreadyDeclaredError` if one stands, or
    :class:`NotReadyError` (with every failing reason) otherwise."""
    if await is_cutover_declared(session):
        raise AlreadyDeclaredError(
            "a cutover declaration already exists; the decommission gate is open"
        )

    readiness = await build_readiness(session, cutover_date=cutover_date)
    if not readiness.ready:
        raise NotReadyError(readiness.reasons)

    # ready == True implies both prerequisite rows exist (asserted above).
    assert readiness.archive_manifest_id is not None
    assert readiness.opening_balance_outbox_id is not None

    row = GlDecommissionCutover(
        cutover_date=cutover_date,
        archive_manifest_id=readiness.archive_manifest_id,
        opening_balance_outbox_id=readiness.opening_balance_outbox_id,
        readiness_snapshot=_snapshot(readiness),
        declared_by_user_id=actor_user_id,
    )
    session.add(row)
    await session.flush()
    return row
