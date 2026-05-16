"""Recurring invoices API (Phase 7.5, #113).

Thin layer over ``app.services.recurring_invoices``. Routers commit the
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
from app.models.recurring_invoice import (
    RecurringCadenceKind,
    RecurringInvoiceItemKind,
    RecurringInvoiceTemplate,
    RecurringInvoiceTemplateItem,
    RecurringTemplateState,
)
from app.schemas.recurring_invoices import (
    RecurringInvoiceMaterializeResponse,
    RecurringTemplateCreate,
    RecurringTemplateItemResponse,
    RecurringTemplateListResponse,
    RecurringTemplateResponse,
    RecurringTemplateStateTransitionRequest,
    RecurringTemplateUpdate,
)
from app.services import recurring_invoices as service

router = APIRouter(prefix="/recurring-invoices", tags=["recurring-invoices"])

_WRITE_ROLES = ("owner", "bookkeeper", "sales")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_item(item: RecurringInvoiceTemplateItem) -> RecurringTemplateItemResponse:
    return RecurringTemplateItemResponse(
        id=item.id,
        line_number=item.line_number,
        kind=(item.kind.value if isinstance(item.kind, RecurringInvoiceItemKind) else item.kind),  # type: ignore[arg-type]
        product_id=item.product_id,
        job_id=item.job_id,
        description=item.description,
        sku_or_job_number=item.sku_or_job_number,
        quantity=item.quantity,
        unit_price=item.unit_price,
    )


def _to_response(template: RecurringInvoiceTemplate) -> RecurringTemplateResponse:
    return RecurringTemplateResponse(
        id=template.id,
        customer_id=template.customer_id,
        name=template.name,
        cadence_kind=(
            template.cadence_kind.value
            if isinstance(template.cadence_kind, RecurringCadenceKind)
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
            if isinstance(template.state, RecurringTemplateState)
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
    if isinstance(exc, service.RecurringTemplateNotFoundError):
        return HTTPException(status_code=404, detail="recurring template not found")
    if isinstance(exc, service.CustomerNotFoundForTemplateError):
        return HTTPException(status_code=400, detail=f"customer not found: {exc}")
    if isinstance(exc, service.InvalidTemplateItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidTemplateStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.RecurringInvoiceServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=RecurringTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: RecurringTemplateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> RecurringTemplateResponse:
    try:
        template = await service.create(
            session,
            customer_id=payload.customer_id,
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


@router.get("", response_model=RecurringTemplateListResponse)
async def list_templates(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RecurringTemplateListResponse:
    try:
        page = await service.list_templates(
            session, state=state, customer_id=customer_id, cursor=cursor, limit=limit
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return RecurringTemplateListResponse(
        items=[_to_response(t) for t in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{template_id}", response_model=RecurringTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> RecurringTemplateResponse:
    try:
        template = await service.get(session, template_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(template)


@router.patch("/{template_id}", response_model=RecurringTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: RecurringTemplateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> RecurringTemplateResponse:
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


@router.post("/{template_id}/pause", response_model=RecurringTemplateResponse)
async def pause_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: RecurringTemplateStateTransitionRequest | None = None,
) -> RecurringTemplateResponse:
    try:
        await service.pause(session, template_id=template_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return _to_response(template)


@router.post("/{template_id}/resume", response_model=RecurringTemplateResponse)
async def resume_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: RecurringTemplateStateTransitionRequest | None = None,
) -> RecurringTemplateResponse:
    try:
        await service.resume(session, template_id=template_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return _to_response(template)


@router.post("/{template_id}/cancel", response_model=RecurringTemplateResponse)
async def cancel_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: RecurringTemplateStateTransitionRequest | None = None,
) -> RecurringTemplateResponse:
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
    response_model=RecurringInvoiceMaterializeResponse,
)
async def materialize_now(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> RecurringInvoiceMaterializeResponse:
    try:
        invoice = await service.materialize_now(
            session, template_id=template_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    template = await service.get(session, template_id)
    return RecurringInvoiceMaterializeResponse(
        template_id=template_id,
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        materialized_at=datetime.now(UTC),
        auto_issued=template.auto_issue,
        next_issue_at=template.next_issue_at,
    )
