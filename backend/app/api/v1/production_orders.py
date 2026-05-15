"""Production orders API (Phase 5.5, #81).

Thin layer over ``app.services.production_orders``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.production_order import ProductionOrder
from app.schemas.production_orders import (
    JobMembershipRequest,
    JobReorderRequest,
    ProductionOrderCreate,
    ProductionOrderJobMember,
    ProductionOrderListResponse,
    ProductionOrderResponse,
    ProductionOrderUpdate,
)
from app.services import production_orders as po_service

router = APIRouter(prefix="/production-orders", tags=["production-orders"])


def _to_response(order: ProductionOrder) -> ProductionOrderResponse:
    return ProductionOrderResponse(
        id=order.id,
        order_number=order.order_number,
        name=order.name,
        state=order.state.value,  # type: ignore[arg-type]
        priority=order.priority,
        due_at=order.due_at,
        notes=order.notes,
        created_by_user_id=order.created_by_user_id,
        created_at=order.created_at,
        updated_at=order.updated_at,
        jobs=[
            ProductionOrderJobMember(job_id=m.job_id, display_order=m.display_order)
            for m in sorted(order.jobs, key=lambda m: m.display_order)
        ],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(
        exc, po_service.ProductionOrderNotFoundError | po_service.JobNotFoundError
    ):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, po_service.InvalidProductionOrderStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, po_service.JobAlreadyInActiveOrderError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, po_service.JobAlreadyInOrderError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, po_service.JobNotInOrderError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, po_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, po_service.ProductionOrdersServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=ProductionOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_production_order(
    payload: ProductionOrderCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        order = await po_service.create(
            session,
            name=payload.name,
            priority=payload.priority,
            due_at=payload.due_at,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(order)


@router.get("", response_model=ProductionOrderListResponse)
async def list_production_orders(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
    state: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ProductionOrderListResponse:
    try:
        page = await po_service.list_orders(
            session, state=state, search=search, cursor=cursor, limit=limit
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return ProductionOrderListResponse(
        items=[_to_response(o) for o in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{order_id}", response_model=ProductionOrderResponse)
async def get_production_order(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> ProductionOrderResponse:
    try:
        order = await po_service.get(session, order_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(order)


@router.patch("/{order_id}", response_model=ProductionOrderResponse)
async def update_production_order(
    order_id: uuid.UUID,
    payload: ProductionOrderUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        order = await po_service.update(
            session, order_id=order_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    order = await po_service.get(session, order.id)
    return _to_response(order)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


@router.post("/{order_id}/activate", response_model=ProductionOrderResponse)
async def activate_production_order(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        await po_service.activate(session, order_id=order_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    order = await po_service.get(session, order_id)
    return _to_response(order)


@router.post("/{order_id}/complete", response_model=ProductionOrderResponse)
async def complete_production_order(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        await po_service.complete(session, order_id=order_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    order = await po_service.get(session, order_id)
    return _to_response(order)


@router.post("/{order_id}/archive", response_model=ProductionOrderResponse)
async def archive_production_order(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        await po_service.archive(session, order_id=order_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    order = await po_service.get(session, order_id)
    return _to_response(order)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


@router.post("/{order_id}/jobs", response_model=ProductionOrderResponse, status_code=201)
async def add_job_to_order(
    order_id: uuid.UUID,
    payload: JobMembershipRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        order = await po_service.add_job(
            session,
            order_id=order_id,
            job_id=payload.job_id,
            display_order=payload.display_order,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(order)


@router.delete(
    "/{order_id}/jobs/{job_id}",
    response_model=ProductionOrderResponse,
)
async def remove_job_from_order(
    order_id: uuid.UUID,
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        order = await po_service.remove_job(
            session, order_id=order_id, job_id=job_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(order)


@router.patch("/{order_id}/jobs", response_model=ProductionOrderResponse)
async def reorder_job_in_order(
    order_id: uuid.UUID,
    payload: JobReorderRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> ProductionOrderResponse:
    try:
        order = await po_service.reorder(
            session,
            order_id=order_id,
            job_id=payload.job_id,
            new_position=payload.new_position,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(order)
