"""Tax-remittance API (Phase 9.6, #158).

Thin layer over ``app.services.tax_remittances``.

Roles
-----
* write (POST / cancel): owner + bookkeeper
* read (GET / list): owner + bookkeeper + sales + viewer
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.tax_remittances import (
    TaxRemittanceCreate,
    TaxRemittanceListResponse,
    TaxRemittanceResponse,
)
from app.services import tax_remittances as service

router = APIRouter(prefix="/tax-remittances", tags=["tax-remittances"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.TaxRemittanceNotFoundError):
        return HTTPException(status_code=404, detail="tax remittance not found")
    if isinstance(exc, service.TaxRemittancePartialBlockedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, service.TaxRemittanceStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, service.InvalidTaxRemittanceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.TaxRemittanceServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=TaxRemittanceResponse, status_code=status.HTTP_201_CREATED)
async def create_remittance(
    payload: TaxRemittanceCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxRemittanceResponse:
    try:
        remittance = await service.record(
            session=session,
            profile_id=payload.profile_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            amount_paid=payload.amount_paid,
            paid_on=payload.paid_on,
            method=payload.method,
            bank_account_id=payload.bank_account_id,
            reference_number=payload.reference_number,
            notes=payload.notes,
            allow_partial=payload.allow_partial,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    fresh = await service.get(session, remittance.id)
    return TaxRemittanceResponse.model_validate(fresh)


@router.get("", response_model=TaxRemittanceListResponse)
async def list_remittances(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    profile_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    paid_from: Annotated[date_type | None, Query()] = None,
    paid_to: Annotated[date_type | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaxRemittanceListResponse:
    try:
        page = await service.list_remittances(
            session,
            profile_id=profile_id,
            state=state,
            paid_from=paid_from,
            paid_to=paid_to,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return TaxRemittanceListResponse(
        items=[TaxRemittanceResponse.model_validate(r) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{remittance_id}", response_model=TaxRemittanceResponse)
async def get_remittance(
    remittance_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> TaxRemittanceResponse:
    try:
        remittance = await service.get(session, remittance_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return TaxRemittanceResponse.model_validate(remittance)


@router.post("/{remittance_id}/cancel", response_model=TaxRemittanceResponse)
async def cancel_remittance(
    remittance_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxRemittanceResponse:
    try:
        remittance = await service.cancel(
            session=session,
            remittance_id=remittance_id,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    fresh = await service.get(session, remittance.id)
    return TaxRemittanceResponse.model_validate(fresh)
