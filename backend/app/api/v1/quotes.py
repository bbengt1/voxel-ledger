"""Quotes API (Phase 7.2, #110).

Thin layer over ``app.services.quotes``. Routers commit the transaction,
map service-layer errors to HTTP, and gate each route on role:

* write (create / update / state transitions): owner + bookkeeper + sales
* read (list / get): owner + bookkeeper + sales + viewer

The ``POST /api/v1/quotes/{id}/convert-to-invoice`` endpoint returns
HTTP 501 until Phase 7.3 (#111) lands the invoice service. The seam is
already in place on the model + state machine.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.quote import Quote, QuoteItem, QuoteItemKind
from app.schemas.customers import CustomerAddress
from app.schemas.quotes import (
    QuoteCreate,
    QuoteItemResponse,
    QuoteListResponse,
    QuoteResponse,
    QuoteStateTransitionRequest,
    QuoteUpdate,
)
from app.services import quotes as quotes_service

router = APIRouter(prefix="/quotes", tags=["quotes"])

_WRITE_ROLES = ("owner", "bookkeeper", "sales")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_item(item: QuoteItem) -> QuoteItemResponse:
    return QuoteItemResponse(
        id=item.id,
        line_number=item.line_number,
        kind=(item.kind.value if isinstance(item.kind, QuoteItemKind) else item.kind),  # type: ignore[arg-type]
        product_id=item.product_id,
        job_id=item.job_id,
        description=item.description,
        sku_or_job_number=item.sku_or_job_number,
        quantity=item.quantity,
        unit_price=item.unit_price,
        extended_amount=item.extended_amount,
    )


def _to_response(quote: Quote) -> QuoteResponse:
    snapshot = (
        CustomerAddress(**quote.billing_address_snapshot)
        if quote.billing_address_snapshot
        else None
    )
    return QuoteResponse(
        id=quote.id,
        quote_number=quote.quote_number,
        customer_id=quote.customer_id,
        state=quote.state.value,  # type: ignore[arg-type]
        issued_at=quote.issued_at,
        valid_until=quote.valid_until,
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
        total_amount=quote.total_amount,
        notes=quote.notes,
        billing_address_snapshot=snapshot,
        accepted_invoice_id=quote.accepted_invoice_id,
        created_by_user_id=quote.created_by_user_id,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        items=[_to_item(i) for i in sorted(quote.items, key=lambda x: x.line_number)],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, quotes_service.QuoteNotFoundError):
        return HTTPException(status_code=404, detail="quote not found")
    if isinstance(exc, quotes_service.CustomerNotFoundForQuoteError):
        return HTTPException(status_code=400, detail=f"customer not found: {exc}")
    if isinstance(exc, quotes_service.InvalidQuoteItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, quotes_service.InvalidQuoteStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, quotes_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, quotes_service.QuotesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: QuoteCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> QuoteResponse:
    try:
        quote = await quotes_service.create_draft(
            session,
            customer_id=payload.customer_id,
            valid_until=payload.valid_until,
            discount_amount=payload.discount_amount,
            tax_amount=payload.tax_amount,
            notes=payload.notes,
            items=[item.model_dump() for item in payload.items],
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    quote = await quotes_service.get(session, quote.id)
    return _to_response(quote)


@router.get("", response_model=QuoteListResponse)
async def list_quotes(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> QuoteListResponse:
    try:
        page = await quotes_service.list_quotes(
            session,
            state=state,
            customer_id=customer_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return QuoteListResponse(
        items=[_to_response(q) for q in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> QuoteResponse:
    try:
        quote = await quotes_service.get(session, quote_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(quote)


@router.patch("/{quote_id}", response_model=QuoteResponse)
async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> QuoteResponse:
    patch_dict = payload.model_dump(exclude_unset=True)
    try:
        await quotes_service.update_draft(
            session, quote_id=quote_id, patch=patch_dict, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    quote = await quotes_service.get(session, quote_id)
    return _to_response(quote)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def _do_transition(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    fn,
) -> QuoteResponse:
    try:
        await fn(session, quote_id=quote_id, actor_user_id=actor_user_id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    quote = await quotes_service.get(session, quote_id)
    return _to_response(quote)


@router.post("/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: QuoteStateTransitionRequest | None = None,
) -> QuoteResponse:
    return await _do_transition(
        session, quote_id=quote_id, actor_user_id=actor.id, fn=quotes_service.send
    )


@router.post("/{quote_id}/accept", response_model=QuoteResponse)
async def accept_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: QuoteStateTransitionRequest | None = None,
) -> QuoteResponse:
    return await _do_transition(
        session, quote_id=quote_id, actor_user_id=actor.id, fn=quotes_service.accept
    )


@router.post("/{quote_id}/decline", response_model=QuoteResponse)
async def decline_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: QuoteStateTransitionRequest | None = None,
) -> QuoteResponse:
    return await _do_transition(
        session, quote_id=quote_id, actor_user_id=actor.id, fn=quotes_service.decline
    )


@router.post("/{quote_id}/expire", response_model=QuoteResponse)
async def expire_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: QuoteStateTransitionRequest | None = None,
) -> QuoteResponse:
    return await _do_transition(
        session, quote_id=quote_id, actor_user_id=actor.id, fn=quotes_service.expire
    )


@router.post("/{quote_id}/cancel", response_model=QuoteResponse)
async def cancel_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: QuoteStateTransitionRequest | None = None,
) -> QuoteResponse:
    return await _do_transition(
        session, quote_id=quote_id, actor_user_id=actor.id, fn=quotes_service.cancel
    )


@router.post("/{quote_id}/convert-to-invoice", status_code=status.HTTP_201_CREATED)
async def convert_quote_to_invoice(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: QuoteStateTransitionRequest | None = None,
):
    """Convert an accepted quote into an invoice (Phase 7.3, #111).

    Returns ``{"invoice_id": "..."}`` and a 201 status. The quote must
    be in state ``accepted`` and not yet have an invoice attached.
    """
    try:
        invoice_id = await quotes_service.convert_to_invoice(
            session, quote_id=quote_id, actor_user_id=actor.id
        )
    except quotes_service.QuoteNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="quote not found") from None
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return {"invoice_id": str(invoice_id)}
