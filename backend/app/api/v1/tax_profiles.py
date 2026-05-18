"""Tax-profile API (Phase 9.5, #157).

Thin layer over ``app.services.tax``. Roles:

* write (POST / PATCH / archive / rate CRUD): owner + bookkeeper
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
from app.schemas.tax_profiles import (
    TaxProfileCreate,
    TaxProfileListResponse,
    TaxProfileResponse,
    TaxProfileUpdate,
    TaxRateCreate,
    TaxRateResponse,
    TaxRateUpdate,
)
from app.services import tax as tax_service

router = APIRouter(prefix="/tax-profiles", tags=["tax-profiles"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, tax_service.TaxProfileNotFoundError):
        return HTTPException(status_code=404, detail="tax profile not found")
    if isinstance(exc, tax_service.TaxRateNotFoundError):
        return HTTPException(status_code=404, detail="tax rate not found")
    if isinstance(exc, tax_service.DuplicateTaxProfileError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, tax_service.InvalidTaxProfileError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, tax_service.TaxServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=TaxProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile_endpoint(
    payload: TaxProfileCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxProfileResponse:
    try:
        profile = await tax_service.create_profile(
            session,
            code=payload.code,
            name=payload.name,
            jurisdiction=payload.jurisdiction,
            is_reverse_charge=payload.is_reverse_charge,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    profile = await tax_service.get_profile(session, profile.id)
    return TaxProfileResponse.model_validate(profile)


@router.get("", response_model=TaxProfileListResponse)
async def list_profiles_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> TaxProfileListResponse:
    profiles = await tax_service.list_profiles(session, active=active, search=search, limit=limit)
    return TaxProfileListResponse(items=[TaxProfileResponse.model_validate(p) for p in profiles])


@router.get("/{profile_id}", response_model=TaxProfileResponse)
async def get_profile_endpoint(
    profile_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> TaxProfileResponse:
    try:
        profile = await tax_service.get_profile(session, profile_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return TaxProfileResponse.model_validate(profile)


@router.patch("/{profile_id}", response_model=TaxProfileResponse)
async def update_profile_endpoint(
    profile_id: uuid.UUID,
    payload: TaxProfileUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxProfileResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        await tax_service.update_profile(
            session, profile_id=profile_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    profile = await tax_service.get_profile(session, profile_id)
    return TaxProfileResponse.model_validate(profile)


@router.post("/{profile_id}/archive", response_model=TaxProfileResponse)
async def archive_profile_endpoint(
    profile_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxProfileResponse:
    try:
        await tax_service.archive_profile(session, profile_id=profile_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    profile = await tax_service.get_profile(session, profile_id)
    return TaxProfileResponse.model_validate(profile)


@router.post(
    "/{profile_id}/rates",
    response_model=TaxRateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_rate_endpoint(
    profile_id: uuid.UUID,
    payload: TaxRateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxRateResponse:
    try:
        rate = await tax_service.add_rate(
            session,
            profile_id=profile_id,
            ordinal=payload.ordinal,
            name=payload.name,
            rate=payload.rate,
            liability_account_id=payload.liability_account_id,
            compound_on_previous=payload.compound_on_previous,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return TaxRateResponse.model_validate(rate)


@router.patch("/{profile_id}/rates/{rate_id}", response_model=TaxRateResponse)
async def update_rate_endpoint(
    profile_id: uuid.UUID,
    rate_id: uuid.UUID,
    payload: TaxRateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> TaxRateResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        rate = await tax_service.update_rate(
            session, rate_id=rate_id, patch=patch, actor_user_id=actor.id
        )
        if rate.profile_id != profile_id:
            raise tax_service.TaxRateNotFoundError(str(rate_id))
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return TaxRateResponse.model_validate(rate)


@router.delete("/{profile_id}/rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_endpoint(
    profile_id: uuid.UUID,
    rate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> None:
    try:
        await tax_service.remove_rate(session, rate_id=rate_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return None
