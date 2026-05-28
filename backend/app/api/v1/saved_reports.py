"""Saved reports API (Parity #237).

Per-user filter presets for any report page. The ``filters`` jsonb
is opaque — the backend never interprets it; the frontend that
knows the page sets + restores it.

Scoping is strict per-user: a user can only see + modify rows where
``owner_user_id`` matches their own user id. Owner role doesn't get
a back door into other users' saved presets.

All authenticated roles can use this. There's nothing privileged
about "my month-end P&L".
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.models.saved_report import SavedReport
from app.schemas.saved_reports import (
    SavedReportCreate,
    SavedReportRead,
    SavedReportUpdate,
)

router = APIRouter(prefix="/saved-reports", tags=["saved-reports"])


def _to_read(row: SavedReport) -> SavedReportRead:
    return SavedReportRead(
        id=row.id,
        name=row.name,
        report_kind=row.report_kind,
        filters=row.filters or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post(
    "",
    response_model=SavedReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_saved_report(
    payload: SavedReportCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SavedReportRead:
    row = SavedReport(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name=payload.name.strip(),
        report_kind=payload.report_kind.strip(),
        filters=dict(payload.filters),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"saved report named {payload.name!r} already exists for "
                f"report kind {payload.report_kind!r}"
            ),
        ) from None
    await session.refresh(row, ["updated_at"])
    response = _to_read(row)
    await session.commit()
    return response


@router.get("", response_model=list[SavedReportRead])
async def list_saved_reports(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    report_kind: Annotated[str | None, Query()] = None,
) -> list[SavedReportRead]:
    stmt = (
        select(SavedReport)
        .where(SavedReport.owner_user_id == user.id)
        .order_by(SavedReport.name.asc())
    )
    if report_kind is not None:
        stmt = stmt.where(SavedReport.report_kind == report_kind)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_read(r) for r in rows]


@router.get("/{saved_report_id}", response_model=SavedReportRead)
async def get_saved_report(
    saved_report_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SavedReportRead:
    row = (
        await session.execute(
            select(SavedReport)
            .where(SavedReport.id == saved_report_id)
            .where(SavedReport.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="saved report not found")
    return _to_read(row)


@router.patch("/{saved_report_id}", response_model=SavedReportRead)
async def update_saved_report(
    saved_report_id: uuid.UUID,
    payload: SavedReportUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SavedReportRead:
    row = (
        await session.execute(
            select(SavedReport)
            .where(SavedReport.id == saved_report_id)
            .where(SavedReport.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="saved report not found")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.filters is not None:
        row.filters = dict(payload.filters)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="name conflicts with another preset") from None
    await session.refresh(row, ["updated_at"])
    response = _to_read(row)
    await session.commit()
    return response


@router.delete("/{saved_report_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_saved_report(
    saved_report_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    row = (
        await session.execute(
            select(SavedReport)
            .where(SavedReport.id == saved_report_id)
            .where(SavedReport.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="saved report not found")
    await session.delete(row)
    await session.commit()
