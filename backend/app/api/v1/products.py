"""Products endpoints (Phase 2.3).

Thin layer over ``app.services.products``. The router commits the
transaction, maps service-layer errors to HTTP, and gates each route on
role.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.product import Product
from app.schemas.products import (
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from app.services import bom as bom_service
from app.services import custom_fields as cf_service
from app.services import inventory_alerts as alerts_service
from app.services import product_images as product_images_service
from app.services import products as products_service
from app.services import upc as upc_service

router = APIRouter(prefix="/products", tags=["products"])


def _bom_error_to_http(exc: bom_service.BomServiceError) -> HTTPException:
    """Map create-time BOM errors to HTTP. 404 for missing parent/component/
    item; 400 for everything else (cycle, depth, invalid kind/quantity,
    archived target)."""
    if isinstance(
        exc,
        bom_service.ProductNotFoundError
        | bom_service.ComponentNotFoundError
        | bom_service.BomItemNotFoundError,
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _refresh_for_response(session: AsyncSession, product: Product) -> None:
    await session.refresh(
        product,
        ["created_at", "updated_at", "unit_cost_cached"],
    )


async def _to_response(session: AsyncSession, product: Product) -> ProductResponse:
    per_location = await alerts_service.on_hand_for_entity(
        session=session, entity_kind="product", entity_id=product.id
    )
    total = sum(per_location.values(), start=Decimal("0"))
    return ProductResponse(
        id=product.id,
        sku=product.sku,
        upc=product.upc,
        name=product.name,
        description=product.description,
        unit_price=product.unit_price,
        unit_cost_cached=product.unit_cost_cached,
        weight_grams=product.weight_grams,
        category=product.category,
        total_on_hand=total,
        per_location_on_hand=per_location,
        low_stock_threshold=product.low_stock_threshold,
        is_archived=product.is_archived,
        custom_fields=dict(product.custom_fields or {}),
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> ProductResponse:
    try:
        product = await products_service.create(
            session,
            name=payload.name,
            description=payload.description,
            unit_price=payload.unit_price,
            sku=payload.sku,
            upc=payload.upc,
            weight_grams=payload.weight_grams,
            category=payload.category,
            low_stock_threshold=payload.low_stock_threshold,
            actor_user_id=actor.id,
            custom_fields=payload.custom_fields,
        )
    except (products_service.DuplicateSkuError, products_service.DuplicateUpcError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None

    # Optional create-time BOM. Each component is added in the same
    # transaction; the synchronous product_cost projection keeps
    # unit_cost_cached in sync as the events are appended.
    if payload.bom_items:
        for item in payload.bom_items:
            try:
                await bom_service.add_component(
                    session,
                    parent_product_id=product.id,
                    component_kind=item.component_kind,
                    component_id=item.component_id,
                    quantity=item.quantity,
                    notes=item.notes,
                    actor_user_id=actor.id,
                )
            except bom_service.BomServiceError as exc:
                await session.rollback()
                raise _bom_error_to_http(exc) from None

    await _refresh_for_response(session, product)
    await session.commit()
    return await _to_response(session, product)


@router.get("", response_model=ProductListResponse)
async def list_products(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    search: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ProductListResponse:
    try:
        page = await products_service.list_products(
            session,
            search=search,
            category=category,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except products_service.ProductsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return ProductListResponse(
        items=[await _to_response(session, p) for p in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/upc/generate")
async def generate_upc(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> dict[str, str]:
    """Mint a fresh unused UPC-A. Returns ``{"upc": "<12 digits>"}``."""
    try:
        upc = await upc_service.allocate_unique_upc(session)
    except upc_service.UpcGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return {"upc": upc}


@router.get("/lookup", response_model=ProductResponse)
async def lookup_product(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    code: Annotated[str, Query(min_length=1)],
) -> ProductResponse:
    try:
        product = await products_service.lookup_by_code(session, code)
    except products_service.ProductNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from None
    return await _to_response(session, product)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> ProductResponse:
    try:
        product = await products_service.get(session, product_id)
    except products_service.ProductNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from None
    return await _to_response(session, product)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> ProductResponse:
    patch = payload.model_dump(exclude_unset=True)
    custom_fields = patch.pop("custom_fields", None)
    try:
        product = await products_service.update(
            session,
            product_id=product_id,
            patch=patch,
            actor_user_id=actor.id,
            custom_fields=custom_fields,
        )
    except products_service.ProductNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from None
    except (products_service.DuplicateSkuError, products_service.DuplicateUpcError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    await _refresh_for_response(session, product)
    await session.commit()
    return await _to_response(session, product)


@router.post("/{product_id}/archive", response_model=ProductResponse)
async def archive_product(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> ProductResponse:
    try:
        product = await products_service.archive(
            session, product_id=product_id, actor_user_id=actor.id
        )
    except products_service.ProductNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from None
    await _refresh_for_response(session, product)
    await session.commit()
    return await _to_response(session, product)


@router.post("/{product_id}/unarchive", response_model=ProductResponse)
async def unarchive_product(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> ProductResponse:
    try:
        product = await products_service.unarchive(
            session, product_id=product_id, actor_user_id=actor.id
        )
    except products_service.ProductNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from None
    await _refresh_for_response(session, product)
    await session.commit()
    return await _to_response(session, product)


# ---------------------------------------------------------------------------
# Product image (#259)
# ---------------------------------------------------------------------------


async def _require_product(session: AsyncSession, product_id: uuid.UUID) -> None:
    try:
        await products_service.get(session, product_id)
    except products_service.ProductNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from None


@router.post("/{product_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def upload_product_image(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
    file: Annotated[UploadFile, File()],
) -> None:
    await _require_product(session, product_id)
    content = await file.read()
    try:
        await product_images_service.save(
            session=session,
            product_id=product_id,
            content=content,
            content_type=file.content_type,
        )
    except product_images_service.ProductImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/{product_id}/image")
async def get_product_image(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(get_current_user)],
    size: Annotated[str, Query(pattern="^(full|thumb)$")] = "full",
) -> FileResponse:
    path = await product_images_service.path_for(session=session, product_id=product_id, size=size)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no image")
    return FileResponse(path, media_type="image/webp")


@router.delete("/{product_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_image(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> None:
    await _require_product(session, product_id)
    await product_images_service.delete(session=session, product_id=product_id)
