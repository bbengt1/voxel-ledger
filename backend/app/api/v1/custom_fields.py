"""Custom-fields endpoints (Phase 2.5).

Thin layer over ``app.services.custom_fields``. Owner-gated for
mutations; any authenticated user may list/get.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.custom_field import CustomField
from app.schemas.custom_fields import (
    CustomFieldCreateRequest,
    CustomFieldListResponse,
    CustomFieldResponse,
    CustomFieldUpdateRequest,
)
from app.services import custom_fields as cf_service

router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])


async def _refresh(session: AsyncSession, cf: CustomField) -> None:
    await session.refresh(cf, ["created_at", "updated_at"])


def _to_response(cf: CustomField) -> CustomFieldResponse:
    return CustomFieldResponse.model_validate(cf)


@router.get("", response_model=CustomFieldListResponse)
async def list_custom_fields(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_type: Annotated[str, Query()],
    include_archived: Annotated[bool, Query()] = False,
) -> CustomFieldListResponse:
    try:
        rows = await cf_service.list_for_entity(
            session, entity_type=entity_type, include_archived=include_archived
        )
    except cf_service.InvalidCustomFieldError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return CustomFieldListResponse(items=[_to_response(r) for r in rows])


@router.post("", response_model=CustomFieldResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_field(
    payload: CustomFieldCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> CustomFieldResponse:
    try:
        cf = await cf_service.create(
            session,
            entity_type=payload.entity_type,
            key=payload.key,
            label=payload.label,
            field_type=payload.field_type,
            options=[opt.model_dump() for opt in payload.options] if payload.options else None,
            required=payload.required,
            default_value=payload.default_value,
            display_order=payload.display_order,
            actor_user_id=actor.id,
        )
    except cf_service.DuplicateCustomFieldError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.InvalidCustomFieldError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, cf)
    await session.commit()
    return _to_response(cf)


@router.get("/{custom_field_id}", response_model=CustomFieldResponse)
async def get_custom_field(
    custom_field_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> CustomFieldResponse:
    try:
        cf = await cf_service.get(session, custom_field_id)
    except cf_service.CustomFieldNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="custom_field not found"
        ) from None
    return _to_response(cf)


@router.patch("/{custom_field_id}", response_model=CustomFieldResponse)
async def update_custom_field(
    custom_field_id: uuid.UUID,
    payload: CustomFieldUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> CustomFieldResponse:
    patch = payload.model_dump(exclude_unset=True)
    if "options" in patch and patch["options"] is not None:
        patch["options"] = [
            opt if isinstance(opt, dict) else opt.model_dump() for opt in patch["options"]
        ]
    try:
        cf = await cf_service.update(
            session,
            custom_field_id=custom_field_id,
            patch=patch,
            actor_user_id=actor.id,
        )
    except cf_service.CustomFieldNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="custom_field not found"
        ) from None
    except cf_service.InvalidCustomFieldError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, cf)
    await session.commit()
    return _to_response(cf)


@router.post("/{custom_field_id}/archive", response_model=CustomFieldResponse)
async def archive_custom_field(
    custom_field_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> CustomFieldResponse:
    try:
        cf = await cf_service.archive(
            session, custom_field_id=custom_field_id, actor_user_id=actor.id
        )
    except cf_service.CustomFieldNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="custom_field not found"
        ) from None
    await _refresh(session, cf)
    await session.commit()
    return _to_response(cf)


@router.post("/{custom_field_id}/unarchive", response_model=CustomFieldResponse)
async def unarchive_custom_field(
    custom_field_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> CustomFieldResponse:
    try:
        cf = await cf_service.unarchive(
            session, custom_field_id=custom_field_id, actor_user_id=actor.id
        )
    except cf_service.CustomFieldNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="custom_field not found"
        ) from None
    except cf_service.DuplicateCustomFieldError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, cf)
    await session.commit()
    return _to_response(cf)
