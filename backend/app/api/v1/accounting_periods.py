"""Accounting-periods endpoints (Phase 4.3, #66).

Thin layer over ``app.services.accounting_periods``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role. The lock endpoint is owner-only; all other mutations require
owner or bookkeeper.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.accounting_period import AccountingPeriod
from app.models.auth import User
from app.schemas.accounting_periods import (
    AccountingPeriodCreate,
    AccountingPeriodListResponse,
    AccountingPeriodResponse,
    AccountingPeriodStateLiteral,
    AccountingPeriodUpdate,
)
from app.services import accounting_periods as periods_service

router = APIRouter(prefix="/accounting/periods", tags=["accounting-periods"])


async def _refresh_for_response(session: AsyncSession, period: AccountingPeriod) -> None:
    await session.refresh(period, ["created_at", "updated_at"])


def _to_response(period: AccountingPeriod) -> AccountingPeriodResponse:
    return AccountingPeriodResponse(
        id=period.id,
        name=period.name,
        start_date=period.start_date,
        end_date=period.end_date,
        state=period.state,  # type: ignore[arg-type]
        closed_at=period.closed_at,
        closed_by_user_id=period.closed_by_user_id,
        locked_at=period.locked_at,
        locked_by_user_id=period.locked_by_user_id,
        created_at=period.created_at,
        updated_at=period.updated_at,
    )


def _map_service_error(exc: periods_service.AccountingPeriodsServiceError) -> HTTPException:
    if isinstance(exc, periods_service.AccountingPeriodNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="accounting period not found"
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "",
    response_model=AccountingPeriodResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_period(
    payload: AccountingPeriodCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> AccountingPeriodResponse:
    try:
        period = await periods_service.create(
            payload.name,
            payload.start_date,
            payload.end_date,
            session=session,
            actor_user_id=actor.id,
        )
    except periods_service.AccountingPeriodsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh_for_response(session, period)
    await session.commit()
    return _to_response(period)


@router.get("", response_model=AccountingPeriodListResponse)
async def list_periods(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    state: Annotated[AccountingPeriodStateLiteral | None, Query()] = None,
    year: Annotated[int | None, Query(ge=1900, le=9999)] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AccountingPeriodListResponse:
    try:
        page = await periods_service.list_periods(
            session=session,
            state=state,
            year=year,
            cursor=cursor,
            limit=limit,
        )
    except periods_service.AccountingPeriodsServiceError as exc:
        raise _map_service_error(exc) from None
    return AccountingPeriodListResponse(
        items=[_to_response(p) for p in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{period_id}", response_model=AccountingPeriodResponse)
async def get_period(
    period_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> AccountingPeriodResponse:
    try:
        period = await periods_service.get(period_id, session=session)
    except periods_service.AccountingPeriodsServiceError as exc:
        raise _map_service_error(exc) from None
    return _to_response(period)


@router.patch("/{period_id}", response_model=AccountingPeriodResponse)
async def update_period(
    period_id: uuid.UUID,
    payload: AccountingPeriodUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> AccountingPeriodResponse:
    try:
        period = await periods_service.update(
            period_id,
            name=payload.name,
            session=session,
            actor_user_id=actor.id,
        )
    except periods_service.AccountingPeriodsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh_for_response(session, period)
    await session.commit()
    return _to_response(period)


@router.post("/{period_id}/close", response_model=AccountingPeriodResponse)
async def close_period(
    period_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> AccountingPeriodResponse:
    try:
        period = await periods_service.close(period_id, session=session, actor_user_id=actor.id)
    except periods_service.AccountingPeriodsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh_for_response(session, period)
    await session.commit()
    return _to_response(period)


@router.post("/{period_id}/reopen", response_model=AccountingPeriodResponse)
async def reopen_period(
    period_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> AccountingPeriodResponse:
    try:
        period = await periods_service.reopen(period_id, session=session, actor_user_id=actor.id)
    except periods_service.AccountingPeriodsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh_for_response(session, period)
    await session.commit()
    return _to_response(period)


@router.post("/{period_id}/lock", response_model=AccountingPeriodResponse)
async def lock_period(
    period_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> AccountingPeriodResponse:
    try:
        period = await periods_service.lock(period_id, session=session, actor_user_id=actor.id)
    except periods_service.AccountingPeriodsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh_for_response(session, period)
    await session.commit()
    return _to_response(period)
