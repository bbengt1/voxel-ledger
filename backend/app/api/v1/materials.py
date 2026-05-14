"""Materials & receipts endpoints (Phase 2.1).

Thin layer over ``app.services.materials`` and
``app.services.material_receipts``. The router commits the transaction,
maps service-layer errors to HTTP, and gates each route on role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.schemas.materials import (
    MaterialCreateRequest,
    MaterialDetailResponse,
    MaterialListResponse,
    MaterialReceiptCreateRequest,
    MaterialReceiptListResponse,
    MaterialReceiptResponse,
    MaterialResponse,
    MaterialUpdateRequest,
)
from app.services import custom_fields as cf_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service

router = APIRouter(prefix="/materials", tags=["materials"])


async def _refresh_for_response(session: AsyncSession, material: Material) -> None:
    """Refresh server-side defaults (created_at / updated_at) the same
    way the users router does."""
    await session.refresh(
        material,
        ["created_at", "updated_at", "current_cost_per_gram", "on_hand_grams"],
    )


def _to_material_response(material: Material) -> MaterialResponse:
    return MaterialResponse(
        id=material.id,
        name=material.name,
        brand=material.brand,
        material_type=material.material_type,
        color=material.color,
        density_g_per_cm3=material.density_g_per_cm3,
        current_cost_per_gram=material.current_cost_per_gram,
        on_hand_grams=material.on_hand_grams,
        is_archived=material.is_archived,
        custom_fields=dict(material.custom_fields or {}),
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


def _to_receipt_response(receipt: MaterialReceipt) -> MaterialReceiptResponse:
    return MaterialReceiptResponse(
        id=receipt.id,
        material_id=receipt.material_id,
        received_at=receipt.received_at,
        grams=receipt.grams,
        total_cost=receipt.total_cost,
        unit_cost_at_receipt=receipt.unit_cost_at_receipt,
        vendor=receipt.vendor,
        reference=receipt.reference,
        notes=receipt.notes,
    )


@router.post(
    "",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_material(
    payload: MaterialCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> MaterialResponse:
    try:
        material = await materials_service.create(
            session,
            name=payload.name,
            brand=payload.brand,
            material_type=payload.material_type,
            color=payload.color,
            density_g_per_cm3=payload.density_g_per_cm3,
            actor_user_id=actor.id,
            custom_fields=payload.custom_fields,
        )
    except materials_service.DuplicateMaterialError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    await _refresh_for_response(session, material)
    await session.commit()
    return _to_material_response(material)


@router.get("", response_model=MaterialListResponse)
async def list_materials(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    search: Annotated[str | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MaterialListResponse:
    try:
        page = await materials_service.list_materials(
            session,
            search=search,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except materials_service.MaterialsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return MaterialListResponse(
        items=[_to_material_response(m) for m in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{material_id}", response_model=MaterialDetailResponse)
async def get_material(
    material_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> MaterialDetailResponse:
    try:
        material = await materials_service.get(session, material_id)
    except materials_service.MaterialNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material not found"
        ) from None
    receipts = await materials_service.get_recent_receipts(session, material_id, limit=10)
    base = _to_material_response(material)
    return MaterialDetailResponse(
        **base.model_dump(),
        recent_receipts=[_to_receipt_response(r) for r in receipts],
    )


@router.patch("/{material_id}", response_model=MaterialResponse)
async def update_material(
    material_id: uuid.UUID,
    payload: MaterialUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> MaterialResponse:
    # Pydantic exposes only set fields via ``model_dump(exclude_unset=True)``.
    patch = payload.model_dump(exclude_unset=True)
    custom_fields = patch.pop("custom_fields", None)
    try:
        material = await materials_service.update(
            session,
            material_id=material_id,
            patch=patch,
            actor_user_id=actor.id,
            custom_fields=custom_fields,
        )
    except materials_service.MaterialNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material not found"
        ) from None
    except materials_service.DuplicateMaterialError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    await _refresh_for_response(session, material)
    await session.commit()
    return _to_material_response(material)


@router.post("/{material_id}/archive", response_model=MaterialResponse)
async def archive_material(
    material_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> MaterialResponse:
    try:
        material = await materials_service.archive(
            session, material_id=material_id, actor_user_id=actor.id
        )
    except materials_service.MaterialNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material not found"
        ) from None
    await _refresh_for_response(session, material)
    await session.commit()
    return _to_material_response(material)


@router.post("/{material_id}/unarchive", response_model=MaterialResponse)
async def unarchive_material(
    material_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> MaterialResponse:
    try:
        material = await materials_service.unarchive(
            session, material_id=material_id, actor_user_id=actor.id
        )
    except materials_service.MaterialNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material not found"
        ) from None
    except materials_service.DuplicateMaterialError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, material)
    await session.commit()
    return _to_material_response(material)


@router.post(
    "/{material_id}/receipts",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_receipt(
    material_id: uuid.UUID,
    payload: MaterialReceiptCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> MaterialResponse:
    try:
        await receipts_service.record(
            session,
            material_id=material_id,
            grams=payload.grams,
            total_cost=payload.total_cost,
            vendor=payload.vendor,
            reference=payload.reference,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except materials_service.MaterialNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material not found"
        ) from None
    except (
        receipts_service.InvalidGramsError,
        receipts_service.InvalidTotalCostError,
    ) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    material = await materials_service.get(session, material_id)
    await _refresh_for_response(session, material)
    await session.commit()
    return _to_material_response(material)


@router.get("/{material_id}/receipts", response_model=MaterialReceiptListResponse)
async def list_receipts(
    material_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MaterialReceiptListResponse:
    # 404 if the material doesn't exist (rather than returning an empty page).
    try:
        await materials_service.get(session, material_id)
    except materials_service.MaterialNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material not found"
        ) from None

    try:
        page = await receipts_service.list_for_material(
            session, material_id=material_id, cursor=cursor, limit=limit
        )
    except receipts_service.InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return MaterialReceiptListResponse(
        items=[_to_receipt_response(r) for r in page.items],
        next_cursor=page.next_cursor,
    )
