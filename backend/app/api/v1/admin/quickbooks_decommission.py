"""Admin endpoints for the local-GL decommission (#318, epic #312, Phase 5).

Owner-only, mounted under ``/api/v1/admin/quickbooks``. Phases 5a/5b ship the
safe, additive prerequisites to removing the local ledger:

* ``POST /decommission/archive`` → export the GL + trial-balance snapshot to
  durable storage and record a manifest. (5a)
* ``GET  /decommission/archive`` → list prior archive manifests. (5a)
* ``GET  /decommission/opening-balance`` → dry-run of the cutover JE: per-account
  lines, totals, unmapped accounts. (5b)
* ``POST /decommission/opening-balance`` → enqueue the cutover opening-balance
  JournalEntry to the QBO sync outbox. (5b)
* ``GET  /decommission/readiness`` → composite go/no-go for the cutover. (5c)
* ``POST /decommission/cutover`` → record the owner's cutover declaration — the
  hard gate the destructive sub-phases (5d-5f) require. (5c)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.gl_archive_manifest import GlArchiveManifest
from app.services.quickbooks import archive, decommission, opening_balance
from app.services.quickbooks import outbox as qbo_outbox
from app.services.settings.service import SettingsService

router = APIRouter(prefix="/quickbooks", tags=["admin-quickbooks"])

# Fallback durable-storage root if ``quickbooks.archive_dir`` isn't configured.
_DEFAULT_ARCHIVE_ROOT = "var/gl_archive"


class ArchiveRequest(BaseModel):
    # Books are archived as of this date (default: today). The trial-balance
    # snapshot closes here.
    cutover_date: date | None = None


class ArchiveManifestResponse(BaseModel):
    id: uuid.UUID
    cutover_date: date
    artifact_dir: str
    row_counts: dict[str, int]
    checksums: dict[str, str]
    total_debits: Decimal
    total_credits: Decimal
    balanced: bool
    created_at: datetime

    @classmethod
    def of(cls, m: GlArchiveManifest) -> ArchiveManifestResponse:
        return cls(
            id=m.id,
            cutover_date=m.cutover_date,
            artifact_dir=m.artifact_dir,
            row_counts=m.row_counts,
            checksums=m.checksums,
            total_debits=m.total_debits,
            total_credits=m.total_credits,
            balanced=m.balanced,
            created_at=m.created_at,
        )


class ArchiveListResponse(BaseModel):
    items: list[ArchiveManifestResponse]


async def _resolve_out_dir(session: AsyncSession, cutover: date) -> Path:
    root = await SettingsService.get("quickbooks.archive_dir", session=session)
    base = Path(str(root) if root else _DEFAULT_ARCHIVE_ROOT)
    # Timestamped subdir so repeated runs never overwrite a prior archive.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return base / f"{cutover.isoformat()}_{stamp}"


@router.post(
    "/decommission/archive",
    response_model=ArchiveManifestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_archive(
    body: ArchiveRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> ArchiveManifestResponse:
    cutover = body.cutover_date or datetime.now(UTC).date()
    out_dir = await _resolve_out_dir(session, cutover)
    try:
        manifest = await archive.build_archive(
            session, cutover_date=cutover, out_dir=out_dir, actor_user_id=user.id
        )
    except archive.ArchiveError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    await session.commit()
    return ArchiveManifestResponse.of(manifest)


@router.get("/decommission/archive", response_model=ArchiveListResponse)
async def list_archives(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> ArchiveListResponse:
    rows = await archive.list_manifests(session)
    return ArchiveListResponse(items=[ArchiveManifestResponse.of(m) for m in rows])


# --- Opening-balance seed (Phase 5b) ----------------------------------------


class OpeningBalanceLineResponse(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    type: str
    balance: Decimal
    posting: str
    amount: Decimal
    qbo_account_id: str | None = None


class OpeningBalancePreviewResponse(BaseModel):
    cutover_date: date
    lines: list[OpeningBalanceLineResponse]
    total_debits: Decimal
    total_credits: Decimal
    balanced: bool
    unmapped_codes: list[str]
    existing_status: str | None = None


class OpeningBalanceSeedRequest(BaseModel):
    cutover_date: date | None = None


class OpeningBalanceSeedResponse(BaseModel):
    outbox_id: uuid.UUID
    status: str
    line_count: int
    doc_number: str


def _preview_response(p: opening_balance.OpeningBalancePreview) -> OpeningBalancePreviewResponse:
    return OpeningBalancePreviewResponse(
        cutover_date=p.cutover_date,
        lines=[
            OpeningBalanceLineResponse(
                account_id=line.account_id,
                code=line.code,
                name=line.name,
                type=line.type,
                balance=line.balance,
                posting=line.posting,
                amount=line.amount,
                qbo_account_id=line.qbo_account_id,
            )
            for line in p.lines
        ],
        total_debits=p.total_debits,
        total_credits=p.total_credits,
        balanced=p.balanced,
        unmapped_codes=p.unmapped_codes,
        existing_status=p.existing_status,
    )


@router.get("/decommission/opening-balance", response_model=OpeningBalancePreviewResponse)
async def preview_opening_balance(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
    cutover_date: Annotated[date | None, Query()] = None,
) -> OpeningBalancePreviewResponse:
    cutover = cutover_date or datetime.now(UTC).date()
    preview = await opening_balance.build_preview(session, cutover_date=cutover)
    return _preview_response(preview)


@router.post(
    "/decommission/opening-balance",
    response_model=OpeningBalanceSeedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def seed_opening_balance(
    body: OpeningBalanceSeedRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> OpeningBalanceSeedResponse:
    if not await qbo_outbox.is_enabled(session):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="quickbooks.enabled is off; enable QuickBooks before seeding",
        )
    cutover = body.cutover_date or datetime.now(UTC).date()
    try:
        row = await opening_balance.enqueue_opening_balance(
            session, cutover_date=cutover, actor_user_id=user.id
        )
    except opening_balance.AlreadySeededError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except opening_balance.OpeningBalanceError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    return OpeningBalanceSeedResponse(
        outbox_id=row.id,
        status=row.status,
        line_count=len(row.payload.get("lines", [])),
        doc_number=row.payload.get("doc_number", ""),
    )


# --- Cutover readiness + declaration (Phase 5c) ------------------------------


class ReadinessResponse(BaseModel):
    cutover_date: date
    ready: bool
    reasons: list[str]
    quickbooks_enabled: bool
    reconciliation_ready: bool
    reconciliation: dict
    archive_manifest_id: uuid.UUID | None = None
    archive_balanced: bool
    archive_cutover_date: date | None = None
    opening_balance_outbox_id: uuid.UUID | None = None
    opening_balance_status: str | None = None
    opening_balance_txn_date: date | None = None
    declared: bool


class CutoverRequest(BaseModel):
    cutover_date: date


class CutoverResponse(BaseModel):
    id: uuid.UUID
    cutover_date: date
    archive_manifest_id: uuid.UUID
    opening_balance_outbox_id: uuid.UUID
    created_at: datetime


def _readiness_response(r: decommission.DecommissionReadiness) -> ReadinessResponse:
    return ReadinessResponse(
        cutover_date=r.cutover_date,
        ready=r.ready,
        reasons=r.reasons,
        quickbooks_enabled=r.quickbooks_enabled,
        reconciliation_ready=r.reconciliation_ready,
        reconciliation=r.reconciliation,
        archive_manifest_id=r.archive_manifest_id,
        archive_balanced=r.archive_balanced,
        archive_cutover_date=r.archive_cutover_date,
        opening_balance_outbox_id=r.opening_balance_outbox_id,
        opening_balance_status=r.opening_balance_status,
        opening_balance_txn_date=r.opening_balance_txn_date,
        declared=r.declared,
    )


@router.get("/decommission/readiness", response_model=ReadinessResponse)
async def get_readiness(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
    cutover_date: Annotated[date | None, Query()] = None,
) -> ReadinessResponse:
    cutover = cutover_date or datetime.now(UTC).date()
    readiness = await decommission.build_readiness(session, cutover_date=cutover)
    return _readiness_response(readiness)


@router.post(
    "/decommission/cutover",
    response_model=CutoverResponse,
    status_code=status.HTTP_201_CREATED,
)
async def declare_cutover(
    body: CutoverRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> CutoverResponse:
    try:
        row = await decommission.declare_cutover(
            session, cutover_date=body.cutover_date, actor_user_id=user.id
        )
    except decommission.AlreadyDeclaredError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except decommission.NotReadyError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "cutover preconditions not met", "reasons": exc.reasons},
        ) from exc
    await session.commit()
    return CutoverResponse(
        id=row.id,
        cutover_date=row.cutover_date,
        archive_manifest_id=row.archive_manifest_id,
        opening_balance_outbox_id=row.opening_balance_outbox_id,
        created_at=row.created_at,
    )
