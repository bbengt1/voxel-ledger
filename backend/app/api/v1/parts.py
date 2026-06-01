"""Parts endpoints (assembly-line epic #267, Phase 1).

Thin layer over ``app.services.parts``. The router commits the
transaction, maps service errors to HTTP, and gates each route on role.
Parts are catalog entities only in this phase — no product/job wiring.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.v1.cost_calc import _result_to_response
from app.core.db import get_session
from app.models.auth import User
from app.projections import part_cost as part_cost_projection
from app.schemas.cost_calc import CalcResultResponse
from app.schemas.parts import (
    PartCreateRequest,
    PartListResponse,
    PartResponse,
    PartUpdateRequest,
)
from app.services import entity_images
from app.services import parts as parts_service
from app.services.cost_engine.service import CostEngineService, MissingRateConfigError

router = APIRouter(prefix="/parts", tags=["parts"])

_IMAGE_KIND = "part"


@router.post("", response_model=PartResponse, status_code=status.HTTP_201_CREATED)
async def create_part(
    payload: PartCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> PartResponse:
    try:
        part = await parts_service.create(
            session,
            name=payload.name,
            sku=payload.sku,
            description=payload.description,
            print_minutes=payload.print_minutes,
            setup_minutes=payload.setup_minutes,
            parts_per_run=payload.parts_per_run,
            print_grams_by_material=payload.print_grams_by_material,
            assigned_printer_ids=payload.assigned_printer_ids,
            custom_fields=payload.custom_fields,
            actor_user_id=actor.id,
        )
    except parts_service.DuplicateSkuError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except parts_service.PartsServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await session.commit()
    await session.refresh(part)
    return PartResponse.model_validate(part)


@router.post("/recompute-costs")
async def recompute_part_costs(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> dict[str, int]:
    """Recompute every part's cached cost. Use after changing labor/machine/
    overhead rates, which the event-driven projection doesn't track."""
    count = await part_cost_projection.recompute_all(session, actor_user_id=actor.id)
    await session.commit()
    return {"recomputed": count}


@router.get("", response_model=PartListResponse)
async def list_parts(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    search: Annotated[str | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PartListResponse:
    try:
        page = await parts_service.list_parts(
            session, search=search, is_archived=is_archived, cursor=cursor, limit=limit
        )
    except parts_service.PartsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return PartListResponse(
        items=[PartResponse.model_validate(p) for p in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{part_id}", response_model=PartResponse)
async def get_part(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> PartResponse:
    try:
        part = await parts_service.get(session, part_id)
    except parts_service.PartNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="part not found"
        ) from None
    return PartResponse.model_validate(part)


@router.get("/{part_id}/cost", response_model=CalcResultResponse)
async def get_part_cost(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> CalcResultResponse:
    """Live cost breakdown (material/labor/machine/overhead) for the part."""
    try:
        part = await parts_service.get(session, part_id)
    except parts_service.PartNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="part not found"
        ) from None
    try:
        result = await CostEngineService.calculate_for_part(part, session=session)
    except MissingRateConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return _result_to_response(result)


@router.patch("/{part_id}", response_model=PartResponse)
async def update_part(
    part_id: uuid.UUID,
    payload: PartUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> PartResponse:
    patch = payload.model_dump(exclude_unset=True)
    custom_fields = patch.pop("custom_fields", None)
    try:
        part = await parts_service.update(
            session,
            part_id=part_id,
            patch=patch,
            actor_user_id=actor.id,
            custom_fields=custom_fields,
        )
    except parts_service.PartNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="part not found"
        ) from None
    except parts_service.DuplicateSkuError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except parts_service.PartsServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await session.commit()
    await session.refresh(part)
    return PartResponse.model_validate(part)


@router.post("/{part_id}/archive", response_model=PartResponse)
async def archive_part(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> PartResponse:
    try:
        part = await parts_service.archive(session, part_id=part_id, actor_user_id=actor.id)
    except parts_service.PartNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="part not found"
        ) from None
    await session.commit()
    await session.refresh(part)
    return PartResponse.model_validate(part)


@router.post("/{part_id}/unarchive", response_model=PartResponse)
async def unarchive_part(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> PartResponse:
    try:
        part = await parts_service.unarchive(session, part_id=part_id, actor_user_id=actor.id)
    except parts_service.PartNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="part not found"
        ) from None
    await session.commit()
    await session.refresh(part)
    return PartResponse.model_validate(part)


# ---------------------------------------------------------------------------
# Part image (reuses the generic entity-image service)
# ---------------------------------------------------------------------------


async def _require_part(session: AsyncSession, part_id: uuid.UUID) -> None:
    try:
        await parts_service.get(session, part_id)
    except parts_service.PartNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="part not found"
        ) from None


@router.post("/{part_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def upload_part_image(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
    file: Annotated[UploadFile, File()],
) -> None:
    await _require_part(session, part_id)
    content = await file.read()
    try:
        await entity_images.save(
            session=session,
            kind=_IMAGE_KIND,
            entity_id=part_id,
            content=content,
            content_type=file.content_type,
        )
    except entity_images.EntityImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/{part_id}/image")
async def get_part_image(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(get_current_user)],
    size: Annotated[str, Query(pattern="^(full|thumb)$")] = "full",
) -> FileResponse:
    path = await entity_images.path_for(
        session=session, kind=_IMAGE_KIND, entity_id=part_id, size=size
    )
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no image")
    return FileResponse(path, media_type="image/webp")


@router.delete("/{part_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part_image(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> None:
    await _require_part(session, part_id)
    await entity_images.delete(session=session, kind=_IMAGE_KIND, entity_id=part_id)
