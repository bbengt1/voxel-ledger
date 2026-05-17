"""Recurring bills API (Phase 8.5, #132).

Thin layer over ``app.services.recurring_bills``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on role.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.recurring_bill import (
    RecurringBillCadenceKind,
    RecurringBillItemKind,
    RecurringBillTemplate,
    RecurringBillTemplateItem,
    RecurringBillTemplateState,
)
from app.schemas.recurring_bills import (
    RecurringBillMaterializeResponse,
    RecurringBillTemplateCreate,
    RecurringBillTemplateItemResponse,
    RecurringBillTemplateListResponse,
    RecurringBillTemplateResponse,
    RecurringBillTemplateStateTransitionRequest,
    RecurringBillTemplateUpdate,
)
from app.services import recurring_bills as service

router = APIRouter(prefix="/recurring-bills", tags=["recurring-bills"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_item(item: RecurringBillTemplateItem) -> RecurringBillTemplateItemResponse:
    return RecurringBillTemplateItemResponse(
        id=item.id,
        line_number=item.line_number,
        kind=(item.kind.value if isinstance(item.kind, RecurringBillItemKind) else item.kind),  # type: ignore[arg-type]
        expense_category_id=item.expense_category_id,
        description=item.description,
        vendor_sku=item.vendor_sku,
        quantity=item.quantity,
        unit_price=item.unit_price,
    )


def _to_response(template: RecurringBillTemplate) -> RecurringBillTemplateResponse:
    return RecurringBillTemplateResponse(
        id=template.id,
        vendor_id=template.vendor_id,
        name=template.name,
        cadence_kind=(
            template.cadence_kind.value
            if isinstance(template.cadence_kind, RecurringBillCadenceKind)
            else template.cadence_kind
        ),  # type: ignore[arg-type]
        cadence_interval=template.cadence_interval,
        start_at=template.start_at,
        end_at=template.end_at,
        next_issue_at=template.next_issue_at,
        last_issued_at=template.last_issued_at,
        auto_issue=template.auto_issue,
        state=(
            template.state.value
            if isinstance(template.state, RecurringBillTemplateState)
            else template.state
        ),  # type: ignore[arg-type]
        notes=template.notes,
        discount_amount=template.discount_amount,
        tax_amount=template.tax_amount,
        currency=template.currency,
        created_by_user_id=template.created_by_user_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        items=[_to_item(i) for i in sorted(template.items, key=lambda x: x.line_number)],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.RecurringBillTemplateNotFoundError):
        return HTTPException(status_code=404, detail="recurring bill template not found")
    if isinstance(exc, service.VendorNotFoundForTemplateError):
        return HTTPException(status_code=400, detail=f"vendor not found: {exc}")
    if isinstance(exc, service.InvalidBillTemplateItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidBillTemplateStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.RecurringBillServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=RecurringBillTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: RecurringBillTemplateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> RecurringBillTemplateResponse:
    try:
        template = await service.create(
            session,
            vendor_id=payload.vendor_id,
            name=payload.name,
            cadence_kind=payload.cadence_kind,
            cadence_interval=payload.cadence_interval,
            start_at=payload.start_at,
            end_at=payload.end_at,
            auto_issue=payload.auto_issue,
            notes=payload.notes,
            discount_amount=payload.discount_amount,
            tax_amount=payload.tax_amount,
            currency=payload.currency,
            items=[item.model_dump() for item in payload.items],
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template.id)
    return _to_response(template)


@router.get("", response_model=RecurringBillTemplateListResponse)
async def list_templates(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    vendor_id: Annotated[uuid.UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RecurringBillTemplateListResponse:
    try:
        page = await service.list_templates(
            session, state=state, vendor_id=vendor_id, cursor=cursor, limit=limit
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return RecurringBillTemplateListResponse(
        items=[_to_response(t) for t in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{template_id}", response_model=RecurringBillTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> RecurringBillTemplateResponse:
    try:
        template = await service.get(session, template_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(template)


@router.patch("/{template_id}", response_model=RecurringBillTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: RecurringBillTemplateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> RecurringBillTemplateResponse:
    patch_dict = payload.model_dump(exclude_unset=True)
    try:
        await service.update(
            session,
            template_id=template_id,
            patch=patch_dict,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return _to_response(template)


@router.post("/{template_id}/pause", response_model=RecurringBillTemplateResponse)
async def pause_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: RecurringBillTemplateStateTransitionRequest | None = None,
) -> RecurringBillTemplateResponse:
    try:
        await service.pause(session, template_id=template_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return _to_response(template)


@router.post("/{template_id}/resume", response_model=RecurringBillTemplateResponse)
async def resume_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: RecurringBillTemplateStateTransitionRequest | None = None,
) -> RecurringBillTemplateResponse:
    try:
        await service.resume(session, template_id=template_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return _to_response(template)


@router.post("/{template_id}/cancel", response_model=RecurringBillTemplateResponse)
async def cancel_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: RecurringBillTemplateStateTransitionRequest | None = None,
) -> RecurringBillTemplateResponse:
    try:
        await service.cancel(session, template_id=template_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return _to_response(template)


@router.post(
    "/{template_id}/materialize-now",
    response_model=RecurringBillMaterializeResponse,
)
async def materialize_now(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> RecurringBillMaterializeResponse:
    try:
        bill = await service.materialize_now(
            session, template_id=template_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return RecurringBillMaterializeResponse(
        template_id=template_id,
        bill_id=bill.id,
        bill_number=bill.bill_number,
        materialized_at=datetime.now(UTC),
        auto_issued=template.auto_issue,
        next_issue_at=template.next_issue_at,
    )
