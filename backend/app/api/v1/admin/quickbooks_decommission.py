"""Admin endpoints for the local-GL decommission (#318, epic #312, Phase 5).

Owner-only, mounted under ``/api/v1/admin/quickbooks``. Phase 5a ships the
historical-archive surface — the safe, additive prerequisite to removing the
local ledger:

* ``POST /decommission/archive`` → export the GL + trial-balance snapshot to
  durable storage and record a manifest.
* ``GET  /decommission/archive`` → list prior archive manifests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.gl_archive_manifest import GlArchiveManifest
from app.services.quickbooks import archive
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
