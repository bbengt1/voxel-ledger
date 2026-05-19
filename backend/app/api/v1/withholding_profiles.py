"""Withholding-profile + YTD-report API (Phase 9.7, #159).

Two router groups exported:

* ``router`` — ``/withholding-profiles`` CRUD + the year-end report
  ``/withholding/ytd-by-vendor``.
* ``vendor_ytd_router`` — ``/vendors/{id}/ytd-payments`` lookup helper.

Roles
-----
* write (POST / PATCH / archive): owner + bookkeeper
* read (GET / list / reports): owner + bookkeeper + sales + viewer
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.vendor import Vendor
from app.schemas.withholding import (
    VendorYtdPaymentsResponse,
    WithholdingProfileCreate,
    WithholdingProfileListResponse,
    WithholdingProfileResponse,
    WithholdingProfileUpdate,
    WithholdingYtdReportResponse,
    WithholdingYtdRowResponse,
)
from app.services import withholding as service

router = APIRouter(tags=["withholding-profiles"])
vendor_ytd_router = APIRouter(prefix="/vendors", tags=["withholding-profiles"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.WithholdingProfileNotFoundError):
        return HTTPException(status_code=404, detail="withholding profile not found")
    if isinstance(exc, service.DuplicateWithholdingProfileError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, service.InvalidWithholdingProfileError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.WithholdingServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# --- CRUD ------------------------------------------------------------------


@router.post(
    "/withholding-profiles",
    response_model=WithholdingProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    payload: WithholdingProfileCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> WithholdingProfileResponse:
    try:
        profile = await service.create_profile(
            session,
            code=payload.code,
            name=payload.name,
            jurisdiction=payload.jurisdiction,
            rate=payload.rate,
            liability_account_id=payload.liability_account_id,
            threshold_per_year=payload.threshold_per_year,
            form_kind=payload.form_kind,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    fresh = await service.get_profile(session, profile.id)
    return WithholdingProfileResponse.model_validate(fresh)


@router.get("/withholding-profiles", response_model=WithholdingProfileListResponse)
async def list_profiles(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> WithholdingProfileListResponse:
    rows = await service.list_profiles(session, active=active, search=search, limit=limit)
    return WithholdingProfileListResponse(
        items=[WithholdingProfileResponse.model_validate(r) for r in rows]
    )


@router.get("/withholding-profiles/{profile_id}", response_model=WithholdingProfileResponse)
async def get_profile(
    profile_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> WithholdingProfileResponse:
    try:
        profile = await service.get_profile(session, profile_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return WithholdingProfileResponse.model_validate(profile)


@router.patch("/withholding-profiles/{profile_id}", response_model=WithholdingProfileResponse)
async def update_profile(
    profile_id: uuid.UUID,
    payload: WithholdingProfileUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> WithholdingProfileResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        await service.update_profile(
            session, profile_id=profile_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    fresh = await service.get_profile(session, profile_id)
    return WithholdingProfileResponse.model_validate(fresh)


@router.post(
    "/withholding-profiles/{profile_id}/archive",
    response_model=WithholdingProfileResponse,
)
async def archive_profile(
    profile_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> WithholdingProfileResponse:
    try:
        await service.archive_profile(session, profile_id=profile_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    fresh = await service.get_profile(session, profile_id)
    return WithholdingProfileResponse.model_validate(fresh)


# --- Vendor YTD lookup -----------------------------------------------------


@vendor_ytd_router.get("/{vendor_id}/ytd-payments", response_model=VendorYtdPaymentsResponse)
async def vendor_ytd_payments(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    year: Annotated[int | None, Query(ge=2000, le=2999)] = None,
) -> VendorYtdPaymentsResponse:
    vendor = (
        await session.execute(select(Vendor).where(Vendor.id == vendor_id))
    ).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=404, detail="vendor not found")
    yr = year if year is not None else datetime.now(UTC).year
    total = await service.vendor_ytd_payment_total(session, vendor_id=vendor_id, year=yr)
    return VendorYtdPaymentsResponse(vendor_id=vendor_id, year=yr, total_paid=total)


# --- YTD-by-vendor report --------------------------------------------------


@router.get("/withholding/ytd-by-vendor", response_model=WithholdingYtdReportResponse)
async def ytd_by_vendor(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    year: Annotated[int, Query(ge=2000, le=2999)],
    profile_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    report = await service.build_ytd_report(session, year=year, profile_id=profile_id)
    if format == "csv":
        body = service.ytd_report_to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": (f'attachment; filename="withholding-ytd-{year}.csv"'),
            },
        )
    return WithholdingYtdReportResponse(
        year=report.year,
        rows=[
            WithholdingYtdRowResponse(
                vendor_id=uuid.UUID(row.vendor_id),
                vendor_number=row.vendor_number,
                display_name=row.display_name,
                profile_id=uuid.UUID(row.profile_id) if row.profile_id else None,
                profile_code=row.profile_code,
                form_kind=row.form_kind,
                total_paid=row.total_paid,
                total_withheld=row.total_withheld,
            )
            for row in report.rows
        ],
        grand_total_paid=report.grand_total_paid,
        grand_total_withheld=report.grand_total_withheld,
    )  # type: ignore[return-value]
