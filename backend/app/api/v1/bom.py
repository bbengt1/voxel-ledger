"""BOM endpoints (Phase 2.4).

Mounted under ``/products/{product_id}/bom`` and
``/products/{product_id}/cost-breakdown``. Thin layer over
``app.services.bom`` — service layer owns validation, cycle detection,
and audit events.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.bom import (
    BomItemCreate,
    BomItemResponse,
    BomItemUpdate,
    BomListResponse,
    CostBreakdownComponent,
    CostBreakdownResponse,
)
from app.services import bom as bom_service
from app.services import products as products_service

router = APIRouter(prefix="/products", tags=["bom"])


def _service_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, bom_service.ProductNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    if isinstance(exc, bom_service.ComponentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, bom_service.BomItemNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bom item not found")
    if isinstance(exc, bom_service.BomCycleError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, bom_service.BomDepthLimitError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, bom_service.BomServiceError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _resolved_to_response(resolved: bom_service.ResolvedBomItem) -> BomItemResponse:
    item = resolved.item
    return BomItemResponse(
        id=item.id,
        parent_product_id=item.parent_product_id,
        component_kind=item.component_kind,  # type: ignore[arg-type]
        component_id=item.component_id,
        quantity=item.quantity,
        notes=item.notes,
        resolved_name=resolved.resolved_name,
        resolved_unit_cost=resolved.resolved_unit_cost,
        line_cost=resolved.line_cost,
    )


@router.get("/{product_id}/bom", response_model=BomListResponse)
async def list_bom(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> BomListResponse:
    # Ensure product exists (404 otherwise) — keeps the API tidy when the
    # BOM is empty.
    try:
        await products_service.get(session, product_id)
    except products_service.ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from exc

    resolved = await bom_service.get_bom(session, product_id=product_id)
    items = [_resolved_to_response(r) for r in resolved]
    total: Decimal | None = Decimal("0")
    for r in resolved:
        if r.line_cost is None:
            total = None
            break
        total = (total or Decimal("0")) + r.line_cost
    return BomListResponse(items=items, total_cost=total)


@router.post(
    "/{product_id}/bom",
    response_model=BomItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bom_item(
    product_id: uuid.UUID,
    payload: BomItemCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> BomItemResponse:
    try:
        item = await bom_service.add_component(
            session,
            parent_product_id=product_id,
            component_kind=payload.component_kind,
            component_id=payload.component_id,
            quantity=payload.quantity,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except bom_service.BomServiceError as exc:
        await session.rollback()
        raise _service_error_to_http(exc) from None

    # Resolve for the response.
    name, unit_cost, _ = await bom_service._load_component(
        session,
        component_kind=item.component_kind,
        component_id=item.component_id,
    )
    line_cost: Decimal | None = None
    if unit_cost is not None:
        from decimal import ROUND_HALF_UP

        line_cost = (Decimal(str(item.quantity)) * unit_cost).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    await session.commit()
    return BomItemResponse(
        id=item.id,
        parent_product_id=item.parent_product_id,
        component_kind=item.component_kind,  # type: ignore[arg-type]
        component_id=item.component_id,
        quantity=item.quantity,
        notes=item.notes,
        resolved_name=name,
        resolved_unit_cost=unit_cost,
        line_cost=line_cost,
    )


@router.patch(
    "/{product_id}/bom/{bom_item_id}",
    response_model=BomItemResponse,
)
async def update_bom_item_quantity(
    product_id: uuid.UUID,
    bom_item_id: uuid.UUID,
    payload: BomItemUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> BomItemResponse:
    # Confirm the item belongs to the path product so we don't allow
    # cross-product mutations via a guessed bom_item_id.
    try:
        existing = await bom_service.get_item(session, bom_item_id)
    except bom_service.BomItemNotFoundError as exc:
        raise _service_error_to_http(exc) from None
    if existing.parent_product_id != product_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bom item not found")

    try:
        item = await bom_service.update_component_quantity(
            session,
            bom_item_id=bom_item_id,
            new_quantity=payload.quantity,
            actor_user_id=actor.id,
        )
    except bom_service.BomServiceError as exc:
        await session.rollback()
        raise _service_error_to_http(exc) from None

    name, unit_cost, _ = await bom_service._load_component(
        session,
        component_kind=item.component_kind,
        component_id=item.component_id,
    )
    line_cost: Decimal | None = None
    if unit_cost is not None:
        from decimal import ROUND_HALF_UP

        line_cost = (Decimal(str(item.quantity)) * unit_cost).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    await session.commit()
    return BomItemResponse(
        id=item.id,
        parent_product_id=item.parent_product_id,
        component_kind=item.component_kind,  # type: ignore[arg-type]
        component_id=item.component_id,
        quantity=item.quantity,
        notes=item.notes,
        resolved_name=name,
        resolved_unit_cost=unit_cost,
        line_cost=line_cost,
    )


@router.delete(
    "/{product_id}/bom/{bom_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_bom_item(
    product_id: uuid.UUID,
    bom_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> None:
    try:
        existing = await bom_service.get_item(session, bom_item_id)
    except bom_service.BomItemNotFoundError as exc:
        raise _service_error_to_http(exc) from None
    if existing.parent_product_id != product_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bom item not found")

    try:
        await bom_service.remove_component(session, bom_item_id=bom_item_id, actor_user_id=actor.id)
    except bom_service.BomServiceError as exc:
        await session.rollback()
        raise _service_error_to_http(exc) from None
    await session.commit()


def _tree_to_response(node: bom_service.CostTreeNode) -> CostBreakdownResponse:
    return CostBreakdownResponse(
        product_id=node.product_id,
        resolved_name=node.resolved_name,
        total_cost=node.total_cost,
        truncated_at_depth=node.truncated_at_depth,
        components=[
            CostBreakdownComponent(
                bom_item_id=c.bom_item_id,
                component_kind=c.component_kind,  # type: ignore[arg-type]
                component_id=c.component_id,
                resolved_name=c.resolved_name,
                quantity=c.quantity,
                unit_cost=c.unit_cost,
                line_cost=c.line_cost,
                sub_tree=_tree_to_response(c.sub_tree) if c.sub_tree else None,
            )
            for c in node.components
        ],
    )


@router.get(
    "/{product_id}/cost-breakdown",
    response_model=CostBreakdownResponse,
)
async def get_cost_breakdown(
    product_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> CostBreakdownResponse:
    try:
        tree = await bom_service.compute_cost_tree(session, product_id=product_id)
    except bom_service.ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        ) from exc
    return _tree_to_response(tree)
