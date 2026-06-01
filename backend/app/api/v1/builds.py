"""Build / assembly endpoints (assembly-line epic #267, Phase 5).

Thin layer over ``app.services.builds``. Routers commit the transaction,
map service-layer errors to HTTP, and gate each route on role. A Build
assembles a Product from its Parts + Supplies (decision #2); ``preview``
returns the required components + availability + cost for the UI's
pre-flight.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.build import Build
from app.schemas.builds import (
    BuildCreate,
    BuildListResponse,
    BuildPlanLine,
    BuildPlanResponse,
    BuildPreviewRequest,
    BuildResponse,
    BuildUpdate,
)
from app.services import builds as builds_service
from app.services.builds import BuildPlan

router = APIRouter(prefix="/builds", tags=["builds"])


def _build_to_response(build: Build) -> BuildResponse:
    return BuildResponse(
        id=build.id,
        build_number=build.build_number,
        product_id=build.product_id,
        state=build.state.value,
        quantity=build.quantity,
        assembly_minutes=build.assembly_minutes,
        location_id=build.location_id,
        unit_cost_cached=build.unit_cost_cached,
        total_cost_cached=build.total_cost_cached,
        notes=build.notes,
        actor_user_id=build.actor_user_id,
        created_at=build.created_at,
        updated_at=build.updated_at,
    )


def _plan_to_response(plan: BuildPlan) -> BuildPlanResponse:
    return BuildPlanResponse(
        product_id=plan.product_id,
        quantity=plan.quantity,
        assembly_minutes=plan.assembly_minutes,
        location_id=plan.location_id,
        lines=[
            BuildPlanLine(
                component_kind=line.component_kind,  # type: ignore[arg-type]
                component_id=line.component_id,
                name=line.name,
                quantity_per_product=line.quantity_per_product,
                required_quantity=line.required_quantity,
                on_hand=line.on_hand,
                sufficient=line.sufficient,
                unit_cost=line.unit_cost,
                line_cost=line.line_cost,
            )
            for line in plan.lines
        ],
        component_cost=plan.component_cost,
        assembly_labor_cost=plan.assembly_labor_cost,
        unit_cost=plan.unit_cost,
        total_cost=plan.total_cost,
        can_build=plan.can_build,
    )


def _map_builds_error(exc: Exception) -> HTTPException:
    if isinstance(exc, builds_service.BuildNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, builds_service.InsufficientStockError):
        return HTTPException(
            status_code=409,
            detail={"message": str(exc), "shortfalls": exc.shortfalls},
        )
    if isinstance(exc, builds_service.InvalidBuildStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, builds_service.ProductLookupError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, builds_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, builds_service.BuildsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=BuildResponse, status_code=status.HTTP_201_CREATED)
async def create_build(
    payload: BuildCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> BuildResponse:
    try:
        build = await builds_service.create(
            session,
            product_id=payload.product_id,
            quantity=payload.quantity,
            assembly_minutes=payload.assembly_minutes,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_builds_error(exc) from None
    await session.commit()
    return _build_to_response(build)


@router.get("", response_model=BuildListResponse)
async def list_builds(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
    state: Annotated[str | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BuildListResponse:
    try:
        page = await builds_service.list_builds(
            session,
            state=state,
            product_id=product_id,
            search=search,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_builds_error(exc) from None
    return BuildListResponse(
        items=[_build_to_response(b) for b in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/preview", response_model=BuildPlanResponse)
async def preview_build(
    payload: BuildPreviewRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> BuildPlanResponse:
    """Pre-flight a proposed build: required parts/supplies, on-hand
    availability, shortfalls, and live cost. Read-only — touches no
    inventory."""
    try:
        product = await builds_service._load_product_active(session, payload.product_id)
        location_id = await _resolve_location_or_none(session)
        assembly_minutes = (
            payload.assembly_minutes
            if payload.assembly_minutes is not None
            else (product.assembly_minutes or 0) * payload.quantity
        )
        plan = await builds_service.compute_plan(
            session,
            product=product,
            quantity=payload.quantity,
            assembly_minutes=assembly_minutes,
            location_id=location_id,
        )
    except Exception as exc:
        raise _map_builds_error(exc) from None
    return _plan_to_response(plan)


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(
    build_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> BuildResponse:
    try:
        build = await builds_service.get(session, build_id)
    except Exception as exc:
        raise _map_builds_error(exc) from None
    return _build_to_response(build)


@router.get("/{build_id}/plan", response_model=BuildPlanResponse)
async def get_build_plan(
    build_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> BuildPlanResponse:
    """Live availability + cost for an existing build (e.g. to show
    shortfalls on a draft before completing)."""
    try:
        build = await builds_service.get(session, build_id)
        product = await builds_service._load_product_active(session, build.product_id)
        location_id = await _resolve_location_or_none(session)
        plan = await builds_service.compute_plan(
            session,
            product=product,
            quantity=build.quantity,
            assembly_minutes=build.assembly_minutes,
            location_id=location_id,
        )
    except Exception as exc:
        raise _map_builds_error(exc) from None
    return _plan_to_response(plan)


@router.patch("/{build_id}", response_model=BuildResponse)
async def update_build(
    build_id: uuid.UUID,
    payload: BuildUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> BuildResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        build = await builds_service.update(
            session, build_id=build_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_builds_error(exc) from None
    await session.commit()
    build = await builds_service.get(session, build.id)
    return _build_to_response(build)


@router.post("/{build_id}/complete", response_model=BuildResponse)
async def complete_build(
    build_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> BuildResponse:
    try:
        await builds_service.complete(session, build_id=build_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_builds_error(exc) from None
    await session.commit()
    build = await builds_service.get(session, build_id)
    return _build_to_response(build)


@router.post("/{build_id}/cancel", response_model=BuildResponse)
async def cancel_build(
    build_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> BuildResponse:
    try:
        await builds_service.cancel(session, build_id=build_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_builds_error(exc) from None
    await session.commit()
    build = await builds_service.get(session, build_id)
    return _build_to_response(build)


async def _resolve_location_or_none(session: AsyncSession) -> uuid.UUID | None:
    """Resolve the consumption location for previews; None if none is
    configured yet (so the preview still renders, just not buildable)."""
    from app.services.jobs import ReceivingLocationError, _resolve_consumption_location_id

    try:
        return await _resolve_consumption_location_id(session)
    except ReceivingLocationError:
        return None
