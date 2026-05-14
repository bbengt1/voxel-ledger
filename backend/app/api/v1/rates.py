"""Rates endpoints (Phase 2.2).

Thin layer over ``app.services.rates``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role.

List is a flat-with-filter shape: ``GET /rates?kind=labor`` rather than
a grouped object. Frontend groups rows for display.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.rate import Rate, RateKind
from app.schemas.rates import (
    RateCreateRequest,
    RateListResponse,
    RateResponse,
    RateUpdateRequest,
)
from app.services import custom_fields as cf_service
from app.services import rates as rates_service

router = APIRouter(prefix="/rates", tags=["rates"])


async def _refresh_for_response(session: AsyncSession, rate: Rate) -> None:
    await session.refresh(rate, ["created_at", "updated_at"])


def _to_response(rate: Rate) -> RateResponse:
    return RateResponse(
        id=rate.id,
        name=rate.name,
        kind=rate.kind,
        value=rate.value,
        applies_to_printer_id=rate.applies_to_printer_id,
        is_default_for_kind=rate.is_default_for_kind,
        is_archived=rate.is_archived,
        custom_fields=dict(rate.custom_fields or {}),
        created_at=rate.created_at,
        updated_at=rate.updated_at,
    )


@router.post(
    "",
    response_model=RateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rate(
    payload: RateCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> RateResponse:
    try:
        rate = await rates_service.create(
            session,
            name=payload.name,
            kind=payload.kind,
            value=payload.value,
            applies_to_printer_id=payload.applies_to_printer_id,
            is_default_for_kind=payload.is_default_for_kind,
            actor_user_id=actor.id,
            custom_fields=payload.custom_fields,
        )
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    except rates_service.RatesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, rate)
    await session.commit()
    return _to_response(rate)


@router.get("", response_model=RateListResponse)
async def list_rates(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    kind: Annotated[RateKind | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RateListResponse:
    try:
        page = await rates_service.list_rates(
            session,
            kind=kind,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except rates_service.RatesServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return RateListResponse(
        items=[_to_response(r) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{rate_id}", response_model=RateResponse)
async def get_rate(
    rate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> RateResponse:
    try:
        rate = await rates_service.get(session, rate_id)
    except rates_service.RateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rate not found"
        ) from None
    return _to_response(rate)


@router.patch("/{rate_id}", response_model=RateResponse)
async def update_rate(
    rate_id: uuid.UUID,
    payload: RateUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> RateResponse:
    patch = payload.model_dump(exclude_unset=True)
    custom_fields = patch.pop("custom_fields", None)
    try:
        rate = await rates_service.update(
            session,
            rate_id=rate_id,
            patch=patch,
            actor_user_id=actor.id,
            custom_fields=custom_fields,
        )
    except rates_service.RateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rate not found"
        ) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    await _refresh_for_response(session, rate)
    await session.commit()
    return _to_response(rate)


@router.post("/{rate_id}/set-default", response_model=RateResponse)
async def set_default_rate(
    rate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> RateResponse:
    try:
        rate = await rates_service.set_default(session, rate_id=rate_id, actor_user_id=actor.id)
    except rates_service.RateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rate not found"
        ) from None
    except rates_service.RatesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, rate)
    await session.commit()
    return _to_response(rate)


@router.post("/{rate_id}/archive", response_model=RateResponse)
async def archive_rate(
    rate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> RateResponse:
    try:
        rate = await rates_service.archive(session, rate_id=rate_id, actor_user_id=actor.id)
    except rates_service.RateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rate not found"
        ) from None
    await _refresh_for_response(session, rate)
    await session.commit()
    return _to_response(rate)


@router.post("/{rate_id}/unarchive", response_model=RateResponse)
async def unarchive_rate(
    rate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> RateResponse:
    try:
        rate = await rates_service.unarchive(session, rate_id=rate_id, actor_user_id=actor.id)
    except rates_service.RateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rate not found"
        ) from None
    await _refresh_for_response(session, rate)
    await session.commit()
    return _to_response(rate)
