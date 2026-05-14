"""Form-templates endpoints (Phase 2.5)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.custom_field import FormTemplate
from app.schemas.custom_fields import (
    CustomFieldResponse,
    FormTemplateCreateRequest,
    FormTemplateFieldAddRequest,
    FormTemplateListResponse,
    FormTemplateResolvedResponse,
    FormTemplateResponse,
    FormTemplateUpdateRequest,
)
from app.services import custom_fields as cf_service
from app.services import form_templates as ft_service

router = APIRouter(prefix="/form-templates", tags=["form-templates"])


async def _refresh(session: AsyncSession, tmpl: FormTemplate) -> None:
    await session.refresh(tmpl, ["created_at", "updated_at"])


def _to_response(tmpl: FormTemplate) -> FormTemplateResponse:
    return FormTemplateResponse.model_validate(tmpl)


@router.get("", response_model=FormTemplateListResponse)
async def list_form_templates(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_type: Annotated[str | None, Query()] = None,
    default_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
) -> FormTemplateListResponse:
    try:
        rows = await ft_service.list_templates(
            session,
            entity_type=entity_type,
            default_only=default_only,
            include_archived=include_archived,
        )
    except cf_service.InvalidCustomFieldError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return FormTemplateListResponse(items=[_to_response(r) for r in rows])


@router.post("", response_model=FormTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_form_template(
    payload: FormTemplateCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> FormTemplateResponse:
    try:
        tmpl = await ft_service.create(
            session,
            entity_type=payload.entity_type,
            name=payload.name,
            description=payload.description,
            is_default_for_entity_type=payload.is_default_for_entity_type,
            display_order=payload.display_order,
            actor_user_id=actor.id,
        )
    except cf_service.InvalidCustomFieldError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, tmpl)
    await session.commit()
    return _to_response(tmpl)


@router.get("/{template_id}", response_model=FormTemplateResolvedResponse)
async def get_form_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> FormTemplateResolvedResponse:
    try:
        resolved = await ft_service.get_resolved(session, template_id=template_id)
    except ft_service.FormTemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="form_template not found"
        ) from None
    return FormTemplateResolvedResponse(
        template=_to_response(resolved.template),
        fields=[CustomFieldResponse.model_validate(f) for f in resolved.fields],
    )


@router.patch("/{template_id}", response_model=FormTemplateResponse)
async def update_form_template(
    template_id: uuid.UUID,
    payload: FormTemplateUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> FormTemplateResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        tmpl = await ft_service.update(
            session,
            template_id=template_id,
            patch=patch,
            actor_user_id=actor.id,
        )
    except ft_service.FormTemplateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="form_template not found"
        ) from None
    await _refresh(session, tmpl)
    await session.commit()
    return _to_response(tmpl)


@router.post("/{template_id}/set-default", response_model=FormTemplateResponse)
async def set_default_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> FormTemplateResponse:
    try:
        tmpl = await ft_service.set_default(
            session, template_id=template_id, actor_user_id=actor.id
        )
    except ft_service.FormTemplateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="form_template not found"
        ) from None
    except ft_service.FormTemplatesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, tmpl)
    await session.commit()
    return _to_response(tmpl)


@router.post("/{template_id}/archive", response_model=FormTemplateResponse)
async def archive_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> FormTemplateResponse:
    try:
        tmpl = await ft_service.archive(session, template_id=template_id, actor_user_id=actor.id)
    except ft_service.FormTemplateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="form_template not found"
        ) from None
    await _refresh(session, tmpl)
    await session.commit()
    return _to_response(tmpl)


@router.post(
    "/{template_id}/fields",
    response_model=FormTemplateResolvedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_template_field(
    template_id: uuid.UUID,
    payload: FormTemplateFieldAddRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> FormTemplateResolvedResponse:
    try:
        await ft_service.add_field(
            session,
            template_id=template_id,
            custom_field_id=payload.custom_field_id,
            display_order=payload.display_order,
            actor_user_id=actor.id,
        )
    except ft_service.FormTemplateNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="form_template not found"
        ) from None
    except cf_service.CustomFieldNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="custom_field not found"
        ) from None
    except ft_service.FormTemplatesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    resolved = await ft_service.get_resolved(session, template_id=template_id)
    await session.commit()
    return FormTemplateResolvedResponse(
        template=_to_response(resolved.template),
        fields=[CustomFieldResponse.model_validate(f) for f in resolved.fields],
    )


@router.delete(
    "/{template_id}/fields/{custom_field_id}",
    response_model=FormTemplateResolvedResponse,
)
async def remove_template_field(
    template_id: uuid.UUID,
    custom_field_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> FormTemplateResolvedResponse:
    try:
        await ft_service.remove_field(
            session,
            template_id=template_id,
            custom_field_id=custom_field_id,
            actor_user_id=actor.id,
        )
    except ft_service.FormTemplatesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    resolved = await ft_service.get_resolved(session, template_id=template_id)
    await session.commit()
    return FormTemplateResolvedResponse(
        template=_to_response(resolved.template),
        fields=[CustomFieldResponse.model_validate(f) for f in resolved.fields],
    )
