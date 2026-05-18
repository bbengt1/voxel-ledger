"""Fixed-assets API (Phase 9.1, #153).

Thin layer over ``app.services.fixed_assets``. The router commits the
transaction so :func:`acquire` is same-TX: row + JE + events.

Roles
-----
* write (POST / PATCH / dispose): owner + bookkeeper
* read (GET / list): owner + bookkeeper + sales + viewer
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.fixed_asset import FixedAsset
from app.schemas.depreciation_schedule import (
    DepreciationScheduleEntryResponse,
    DepreciationScheduleResponse,
)
from app.schemas.fixed_assets import (
    FixedAssetAcquireRequest,
    FixedAssetListResponse,
    FixedAssetResponse,
    FixedAssetUpdate,
)
from app.services import depreciation_schedule as schedule_service
from app.services import fixed_assets as fa_service

router = APIRouter(prefix="/fixed-assets", tags=["fixed-assets"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_response(asset: FixedAsset) -> FixedAssetResponse:
    return FixedAssetResponse(
        id=asset.id,
        asset_number=asset.asset_number,
        name=asset.name,
        kind=asset.asset_kind.value,  # type: ignore[arg-type]
        asset_class=asset.asset_class.value,  # type: ignore[arg-type]
        acquired_on=asset.acquired_on,
        acquisition_cost=asset.acquisition_cost,
        salvage_value=asset.salvage_value,
        useful_life_months=asset.useful_life_months,
        depreciation_method=asset.depreciation_method.value,  # type: ignore[arg-type]
        asset_account_id=asset.asset_account_id,
        accumulated_depreciation_account_id=asset.accumulated_depreciation_account_id,
        depreciation_expense_account_id=asset.depreciation_expense_account_id,
        serial_number=asset.serial_number,
        vendor_id=asset.vendor_id,
        acquisition_bill_id=asset.acquisition_bill_id,
        state=asset.state.value,  # type: ignore[arg-type]
        last_depreciated_on=asset.last_depreciated_on,
        posting_journal_entry_id=asset.posting_journal_entry_id,
        notes=asset.notes,
        created_by_user_id=asset.created_by_user_id,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, fa_service.FixedAssetNotFoundError):
        return HTTPException(status_code=404, detail="fixed asset not found")
    if isinstance(exc, fa_service.FixedAssetAccountNotFoundError):
        return HTTPException(status_code=400, detail=f"account not found: {exc}")
    if isinstance(exc, fa_service.InvalidAccountTypeError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, fa_service.InvalidAcquisitionBillError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, fa_service.FixedAssetUpdateNotAllowedError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, fa_service.InvalidFixedAssetInputError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, fa_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, fa_service.FixedAssetServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=FixedAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: FixedAssetAcquireRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> FixedAssetResponse:
    try:
        asset = await fa_service.acquire(
            session=session,
            name=payload.name,
            kind=payload.kind,
            asset_class=payload.asset_class,
            acquired_on=payload.acquired_on,
            acquisition_cost=payload.acquisition_cost,
            salvage_value=payload.salvage_value,
            useful_life_months=payload.useful_life_months,
            depreciation_method=payload.depreciation_method,
            asset_account_id=payload.asset_account_id,
            accumulated_depreciation_account_id=payload.accumulated_depreciation_account_id,
            depreciation_expense_account_id=payload.depreciation_expense_account_id,
            contra_account_id=payload.contra_account_id,
            serial_number=payload.serial_number,
            vendor_id=payload.vendor_id,
            acquisition_bill_id=payload.acquisition_bill_id,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    asset = await fa_service.get(session, asset.id)
    return _to_response(asset)


@router.get("", response_model=FixedAssetListResponse)
async def list_assets(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    kind: Annotated[str | None, Query()] = None,
    asset_class: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FixedAssetListResponse:
    try:
        page = await fa_service.list_assets(
            session,
            kind=kind,
            asset_class=asset_class,
            state=state,
            search=search,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return FixedAssetListResponse(
        items=[_to_response(a) for a in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{asset_id}", response_model=FixedAssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> FixedAssetResponse:
    try:
        asset = await fa_service.get(session, asset_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(asset)


@router.patch("/{asset_id}", response_model=FixedAssetResponse)
async def update_asset(
    asset_id: uuid.UUID,
    payload: FixedAssetUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> FixedAssetResponse:
    patch_dict = payload.model_dump(exclude_unset=True)
    try:
        await fa_service.update(
            session=session,
            asset_id=asset_id,
            patch=patch_dict,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    asset = await fa_service.get(session, asset_id)
    return _to_response(asset)


@router.get(
    "/{asset_id}/depreciation-schedule",
    response_model=DepreciationScheduleResponse,
)
async def get_depreciation_schedule(
    asset_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> DepreciationScheduleResponse:
    try:
        entries = await schedule_service.get_schedule(session=session, asset_id=asset_id)
    except schedule_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"fixed asset not found: {exc}") from None
    except Exception as exc:
        raise _map_error(exc) from None
    from decimal import Decimal as _D

    total = sum((e.depreciation_amount for e in entries), _D("0"))
    return DepreciationScheduleResponse(
        asset_id=asset_id,
        entries=[DepreciationScheduleEntryResponse.model_validate(e) for e in entries],
        total_depreciation=total,
    )


@router.post("/{asset_id}/dispose")
async def dispose_asset(
    asset_id: uuid.UUID,
    _session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> None:
    # Phase 9.1 stubs the dispose endpoint. Implementation lands in 9.4 (#155).
    raise HTTPException(
        status_code=501,
        detail=(
            f"dispose for asset {asset_id} is stubbed in Phase 9.1; "
            "implementation lands in Phase 9.4 (#155)"
        ),
    )
