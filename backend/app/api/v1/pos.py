"""POS API (Phase 6.4, #96).

Thin layer over ``app.services.pos``. Roles:

* write (open / scan / line edits / checkout / void): owner + sales
* read (get): owner + sales + bookkeeper
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.api.v1.sales import _to_response as sale_to_response
from app.core.db import get_session
from app.models.auth import User
from app.models.pos_cart import PosCart, PosCartItem, PosCartState
from app.models.sales_channel import SalesChannel
from app.models.tax_profile import TaxProfile
from app.schemas.pos import (
    AddProductRequest,
    CartTaxProfileRequest,
    CheckoutRequest,
    CheckoutResponse,
    LineUpdateRequest,
    OpenCartRequest,
    PosCartItemResponse,
    PosCartResponse,
    ScanRequest,
)
from app.services import pos as pos_service
from app.services import sales as sales_service
from app.services import tax as tax_service
from app.services.cogs import service as cogs_service

router = APIRouter(prefix="/pos", tags=["pos"])


def _to_item(item: PosCartItem) -> PosCartItemResponse:
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal("0.000001")
    gross = (item.quantity * item.unit_price).quantize(q, rounding=ROUND_HALF_UP)
    if item.discount_kind == "percent":
        disc = (gross * item.discount_amount / Decimal("100")).quantize(q, rounding=ROUND_HALF_UP)
    elif item.discount_kind == "amount":
        disc = Decimal(item.discount_amount).quantize(q, rounding=ROUND_HALF_UP)
    else:
        disc = Decimal("0")
    return PosCartItemResponse(
        id=item.id,
        line_number=item.line_number,
        product_id=item.product_id,
        description=item.description,
        sku=item.sku,
        quantity=item.quantity,
        unit_price=item.unit_price,
        discount_amount=item.discount_amount,
        discount_kind=item.discount_kind,  # type: ignore[arg-type]
        extended_amount=(gross - disc).quantize(q, rounding=ROUND_HALF_UP),
    )


def _to_response(cart: PosCart) -> PosCartResponse:
    totals = pos_service.compute_totals(cart)
    return PosCartResponse(
        id=cart.id,
        cashier_user_id=cart.cashier_user_id,
        channel_id=cart.channel_id,
        state=(cart.state.value if isinstance(cart.state, PosCartState) else cart.state),  # type: ignore[arg-type]
        customer_id=cart.customer_id,
        customer_name=cart.customer_name,
        customer_email=cart.customer_email,
        discount_amount=cart.discount_amount,
        discount_kind=cart.discount_kind,  # type: ignore[arg-type]
        sale_id=cart.sale_id,
        created_at=cart.created_at,
        updated_at=cart.updated_at,
        items=[_to_item(i) for i in sorted(cart.items, key=lambda x: x.line_number)],
        subtotal=totals.subtotal,
        line_discount_total=totals.line_discount_total,
        cart_discount_amount=totals.cart_discount_amount,
        total=totals.total,
    )


async def _to_response_with_tax(
    cart: PosCart, *, session: AsyncSession
) -> PosCartResponse:
    """Build the cart response and overlay a tax preview when the cart's
    channel carries a ``tax_profile_id``. Computes the tax from the
    after-discount ``total`` using the existing :func:`compute_line_tax`
    helper, then exposes a single aggregate ``tax_amount`` plus the
    profile id/name so the UI can label the line."""
    response = _to_response(cart)
    from sqlalchemy.orm import selectinload as _selectinload

    # Per-cart override wins over the channel default.
    profile_id = cart.tax_profile_id
    if profile_id is None:
        channel = (
            await session.execute(
                select(SalesChannel).where(SalesChannel.id == cart.channel_id)
            )
        ).scalar_one_or_none()
        if channel is None:
            return response
        profile_id = channel.tax_profile_id
    if profile_id is None:
        return response
    profile = (
        await session.execute(
            select(TaxProfile)
            .where(TaxProfile.id == profile_id)
            .options(_selectinload(TaxProfile.rates))
        )
    ).scalar_one_or_none()
    if profile is None or not profile.is_active or not profile.rates:
        return response
    per_rate = tax_service.compute_line_tax(
        line_subtotal=response.total, rates=list(profile.rates)
    )
    response.tax_amount = sum((amt for _, amt in per_rate), start=Decimal("0"))
    response.tax_profile_id = profile.id
    response.tax_profile_name = profile.name
    return response


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, pos_service.PosCartNotFoundError):
        return HTTPException(status_code=404, detail="cart not found")
    if isinstance(exc, pos_service.PosBarcodeNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, pos_service.PosLineNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, pos_service.PosChannelNotFoundError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, pos_service.PosCartStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, pos_service.PosServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sales_service.SalesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, cogs_service.CogsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Open
# ---------------------------------------------------------------------------


@router.post("/carts", response_model=PosCartResponse, status_code=status.HTTP_201_CREATED)
async def open_cart(
    payload: OpenCartRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    try:
        cart = await pos_service.open_cart(
            channel_id=payload.channel_id,
            cashier=actor,
            session=session,
            customer_id=payload.customer_id,
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart.id)
    return await _to_response_with_tax(cart, session=session)


@router.get("/carts/{cart_id}", response_model=PosCartResponse)
async def get_cart(
    cart_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
) -> PosCartResponse:
    try:
        cart = await pos_service.get(session, cart_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return await _to_response_with_tax(cart, session=session)


@router.post("/carts/{cart_id}/scan", response_model=PosCartResponse)
async def scan(
    cart_id: uuid.UUID,
    payload: ScanRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    try:
        cart = await pos_service.scan_barcode(
            cart_id, payload.barcode, session=session, actor=actor
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart_id)
    return await _to_response_with_tax(cart, session=session)


@router.post("/carts/{cart_id}/add-product", response_model=PosCartResponse)
async def add_product(
    cart_id: uuid.UUID,
    payload: AddProductRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    try:
        cart = await pos_service.add_product(
            cart_id,
            payload.product_id,
            payload.quantity,
            session=session,
            actor=actor,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart_id)
    return await _to_response_with_tax(cart, session=session)


@router.post("/carts/{cart_id}/tax-profile", response_model=PosCartResponse)
async def set_cart_tax_profile(
    cart_id: uuid.UUID,
    payload: CartTaxProfileRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    """Set or clear the per-cart tax-profile override."""
    try:
        cart = await pos_service.set_cart_tax_profile(
            cart_id,
            payload.tax_profile_id,
            session=session,
            actor=actor,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart_id)
    return await _to_response_with_tax(cart, session=session)


@router.patch("/carts/{cart_id}/lines/{line_number}", response_model=PosCartResponse)
async def update_line(
    cart_id: uuid.UUID,
    line_number: int,
    payload: LineUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    try:
        if payload.quantity is not None:
            await pos_service.set_line_quantity(
                cart_id, line_number, payload.quantity, session=session, actor=actor
            )
        if payload.discount_kind is not None and payload.discount_value is not None:
            await pos_service.apply_discount(
                cart_id,
                kind=payload.discount_kind,
                value=payload.discount_value,
                line_number=line_number,
                session=session,
                actor=actor,
            )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart_id)
    return await _to_response_with_tax(cart, session=session)


@router.delete("/carts/{cart_id}/lines/{line_number}", response_model=PosCartResponse)
async def delete_line(
    cart_id: uuid.UUID,
    line_number: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    try:
        await pos_service.remove_line(cart_id, line_number, session=session, actor=actor)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart_id)
    return await _to_response_with_tax(cart, session=session)


@router.post("/carts/{cart_id}/checkout", response_model=CheckoutResponse)
async def checkout(
    cart_id: uuid.UUID,
    payload: CheckoutRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> CheckoutResponse:
    try:
        result = await pos_service.checkout(
            cart_id,
            payment_method=payload.payment_method,
            tendered_amount=payload.tendered_amount,
            session=session,
            actor=actor,
            customer_id=payload.customer_id,
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
            tax_amount=payload.tax_amount,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    # Reload sale (committed) so items are present.
    sale = await sales_service.get(session, result.sale.id)
    cart = await pos_service.get(session, cart_id)
    return CheckoutResponse(
        sale=sale_to_response(sale),
        change_due=result.change_due,
        cart=await _to_response_with_tax(cart, session=session),
    )


@router.post("/carts/{cart_id}/void", response_model=PosCartResponse)
async def void(
    cart_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> PosCartResponse:
    try:
        await pos_service.void_cart(cart_id, session=session, actor=actor)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    cart = await pos_service.get(session, cart_id)
    return await _to_response_with_tax(cart, session=session)
