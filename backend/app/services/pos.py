"""POS service (Phase 6.4, #96).

A POS cart is a stateful server-side checkout session. Operators open a
cart, scan barcodes (each scan = one indexed product lookup + one
INSERT-or-UPDATE on the cart-item table), optionally apply line / cart
discounts, then checkout — which builds a ``SaleCreate`` from the cart
and calls ``sales_service.create_draft + confirm`` in one transaction so
the Phase 6.3 inventory + journal posting fires atomically.

Performance budget: < 500ms p95 scan-to-server-response. The hot path
(``scan_barcode``) is:

    1. SELECT product WHERE upc = :barcode  (Phase 2 partial unique index)
    2. SELECT existing cart-item by (cart_id, product_id) — same TX
    3. INSERT or UPDATE one row

That is the entire database footprint of one scan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import sales as sales_events
from app.models.auth import User
from app.models.pos_cart import PosCart, PosCartItem, PosCartState
from app.models.product import Product
from app.models.sales_channel import SalesChannel
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import sales as sales_service

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PosServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class PosCartNotFoundError(PosServiceError):
    """Mapped to 404."""


class PosBarcodeNotFoundError(PosServiceError):
    """Mapped to 404 — no product with the supplied barcode."""


class PosCartStateError(PosServiceError):
    """Illegal operation given the cart state (e.g. scan on a checked-out cart)."""


class PosLineNotFoundError(PosServiceError):
    """Mapped to 404 — referenced line_number doesn't exist on the cart."""


class PosChannelNotFoundError(PosServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Totals helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CartTotals:
    subtotal: Decimal
    line_discount_total: Decimal
    cart_discount_amount: Decimal
    total: Decimal


def _line_extended(item: PosCartItem) -> Decimal:
    """Compute (quantity * unit_price) - line discount for one cart item."""
    gross = _q(item.quantity * item.unit_price)
    discount = _line_discount_amount(item, gross)
    return _q(gross - discount)


def _line_discount_amount(item: PosCartItem, gross: Decimal | None = None) -> Decimal:
    if item.discount_kind is None:
        return Decimal("0")
    if gross is None:
        gross = _q(item.quantity * item.unit_price)
    if item.discount_kind == "percent":
        # discount_amount is the percent (e.g. 10 = 10%)
        return _q(gross * item.discount_amount / Decimal("100"))
    # ``amount``
    return _q(item.discount_amount)


def compute_totals(cart: PosCart) -> _CartTotals:
    subtotal_gross = Decimal("0")
    line_disc_total = Decimal("0")
    for item in cart.items:
        gross = _q(item.quantity * item.unit_price)
        subtotal_gross += gross
        line_disc_total += _line_discount_amount(item, gross)
    subtotal_after_lines = _q(subtotal_gross - line_disc_total)

    if cart.discount_kind == "percent":
        cart_disc = _q(subtotal_after_lines * cart.discount_amount / Decimal("100"))
    elif cart.discount_kind == "amount":
        cart_disc = _q(cart.discount_amount)
    else:
        cart_disc = Decimal("0")

    total = _q(subtotal_after_lines - cart_disc)
    if total < 0:
        total = Decimal("0")
    return _CartTotals(
        subtotal=_q(subtotal_gross),
        line_discount_total=_q(line_disc_total),
        cart_discount_amount=cart_disc,
        total=total,
    )


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    cart_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=sales_events.AGGREGATE_TYPE_POS_CART,
            aggregate_id=cart_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, cart_id: uuid.UUID) -> PosCart:
    stmt = select(PosCart).options(selectinload(PosCart.items)).where(PosCart.id == cart_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise PosCartNotFoundError(str(cart_id))
    # Force a fresh items load — the selectinload on a second call inside
    # the same session would otherwise return the cached collection.
    await session.refresh(row, ["items"])
    return row


def _ensure_open(cart: PosCart) -> None:
    if cart.state != PosCartState.OPEN:
        raise PosCartStateError(f"cart {cart.id} is in state {cart.state.value}; expected open")


# ---------------------------------------------------------------------------
# Open
# ---------------------------------------------------------------------------


async def open_cart(
    *,
    channel_id: uuid.UUID,
    cashier: User,
    session: AsyncSession,
    customer_id: uuid.UUID | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
) -> PosCart:
    channel = (
        await session.execute(select(SalesChannel).where(SalesChannel.id == channel_id))
    ).scalar_one_or_none()
    if channel is None:
        raise PosChannelNotFoundError(str(channel_id))

    cart = PosCart(
        cashier_user_id=cashier.id,
        channel_id=channel_id,
        state=PosCartState.OPEN,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_email=customer_email,
    )
    session.add(cart)
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_POS_CART_OPENED,
        cart_id=cart.id,
        payload={
            "cart_id": str(cart.id),
            "channel_id": str(channel_id),
            "cashier_user_id": str(cashier.id),
        },
        actor_user_id=cashier.id,
    )
    # Reload with items collection populated (empty list) for response.
    return await _load(session, cart.id)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


async def _next_line_number(session: AsyncSession, cart_id: uuid.UUID) -> int:
    """Single aggregate query for the next line number on this cart."""
    result = await session.execute(
        select(func.coalesce(func.max(PosCartItem.line_number), 0)).where(
            PosCartItem.cart_id == cart_id
        )
    )
    return int(result.scalar_one() or 0) + 1


async def scan_barcode(
    cart_id: uuid.UUID,
    barcode: str,
    *,
    session: AsyncSession,
    actor: User | None,
) -> PosCart:
    """Scan a barcode into the cart.

    Hot path — minimize round trips:

    * single indexed SELECT on ``product.upc`` (the v2 catalog's barcode
      column; Phase 2 already indexes this with the partial-unique
      ``ux_product_upc_not_null`` index),
    * one SELECT on (cart_id, product_id) to find an existing line,
    * one INSERT or UPDATE.

    Idempotency: scanning the same barcode twice on the same open cart
    increments the existing line's quantity rather than appending a new
    line. Lines are identified by ``(cart_id, line_number)``; the
    line-number allocator is a single ``COALESCE(MAX) + 1`` query so the
    P95 budget holds against a populated catalog.
    """
    cart = await _load(session, cart_id)
    _ensure_open(cart)

    barcode_norm = barcode.strip()
    if not barcode_norm:
        raise PosBarcodeNotFoundError("empty barcode")

    product = (
        await session.execute(select(Product).where(Product.upc == barcode_norm))
    ).scalar_one_or_none()
    if product is None:
        raise PosBarcodeNotFoundError(f"no product with barcode {barcode_norm!r}")

    # Look for an existing line in this cart for this product.
    existing = next((i for i in cart.items if i.product_id == product.id), None)
    if existing is not None:
        existing.quantity = _q(existing.quantity + Decimal("1"))
        await session.flush()
        await _emit(
            session,
            event_type=sales_events.TYPE_POS_LINE_UPDATED,
            cart_id=cart.id,
            payload={
                "cart_id": str(cart.id),
                "line_number": existing.line_number,
                "before": {"quantity": str(_q(existing.quantity - Decimal("1")))},
                "after": {"quantity": str(existing.quantity)},
            },
            actor_user_id=actor.id if actor else None,
        )
    else:
        line_number = await _next_line_number(session, cart.id)
        item = PosCartItem(
            cart_id=cart.id,
            line_number=line_number,
            product_id=product.id,
            description=product.name,
            sku=product.sku,
            quantity=Decimal("1"),
            unit_price=product.unit_price,
        )
        session.add(item)
        await session.flush()
        await _emit(
            session,
            event_type=sales_events.TYPE_POS_LINE_ADDED,
            cart_id=cart.id,
            payload={
                "cart_id": str(cart.id),
                "line_number": line_number,
                "product_id": str(product.id),
                "sku": product.sku,
                "quantity": "1",
                "unit_price": str(product.unit_price),
            },
            actor_user_id=actor.id if actor else None,
        )
    return await _load(session, cart.id)


# ---------------------------------------------------------------------------
# Line management
# ---------------------------------------------------------------------------


def _find_line(cart: PosCart, line_number: int) -> PosCartItem:
    for item in cart.items:
        if item.line_number == line_number:
            return item
    raise PosLineNotFoundError(f"line {line_number} not found on cart {cart.id}")


async def set_line_quantity(
    cart_id: uuid.UUID,
    line_number: int,
    quantity: Decimal | str | int | float,
    *,
    session: AsyncSession,
    actor: User | None,
) -> PosCart:
    cart = await _load(session, cart_id)
    _ensure_open(cart)
    item = _find_line(cart, line_number)
    new_qty = _q(quantity)
    if new_qty <= 0:
        raise PosServiceError("quantity must be positive; use DELETE to remove a line")
    before = str(item.quantity)
    item.quantity = new_qty
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_POS_LINE_UPDATED,
        cart_id=cart.id,
        payload={
            "cart_id": str(cart.id),
            "line_number": line_number,
            "before": {"quantity": before},
            "after": {"quantity": str(item.quantity)},
        },
        actor_user_id=actor.id if actor else None,
    )
    return await _load(session, cart.id)


async def remove_line(
    cart_id: uuid.UUID,
    line_number: int,
    *,
    session: AsyncSession,
    actor: User | None,
) -> PosCart:
    cart = await _load(session, cart_id)
    _ensure_open(cart)
    item = _find_line(cart, line_number)
    await session.delete(item)
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_POS_LINE_REMOVED,
        cart_id=cart.id,
        payload={"cart_id": str(cart.id), "line_number": line_number},
        actor_user_id=actor.id if actor else None,
    )
    return await _load(session, cart.id)


async def apply_discount(
    cart_id: uuid.UUID,
    *,
    kind: str,
    value: Decimal | str | int | float,
    line_number: int | None = None,
    session: AsyncSession,
    actor: User | None,
) -> PosCart:
    if kind not in ("percent", "amount"):
        raise PosServiceError(f"invalid discount kind {kind!r}")
    amount = _q(value)
    if amount < 0:
        raise PosServiceError("discount value must be non-negative")
    cart = await _load(session, cart_id)
    _ensure_open(cart)
    if line_number is not None:
        item = _find_line(cart, line_number)
        before = {"discount_kind": item.discount_kind, "discount_amount": str(item.discount_amount)}
        item.discount_kind = kind
        item.discount_amount = amount
        await session.flush()
        await _emit(
            session,
            event_type=sales_events.TYPE_POS_LINE_UPDATED,
            cart_id=cart.id,
            payload={
                "cart_id": str(cart.id),
                "line_number": line_number,
                "before": before,
                "after": {"discount_kind": kind, "discount_amount": str(amount)},
            },
            actor_user_id=actor.id if actor else None,
        )
    else:
        before = {"discount_kind": cart.discount_kind, "discount_amount": str(cart.discount_amount)}
        cart.discount_kind = kind
        cart.discount_amount = amount
        await session.flush()
        await _emit(
            session,
            event_type=sales_events.TYPE_POS_LINE_UPDATED,
            cart_id=cart.id,
            payload={
                "cart_id": str(cart.id),
                "line_number": 0,
                "before": before,
                "after": {"discount_kind": kind, "discount_amount": str(amount)},
            },
            actor_user_id=actor.id if actor else None,
        )
    return await _load(session, cart.id)


# ---------------------------------------------------------------------------
# Checkout / Void
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckoutResult:
    sale: Any  # Sale model
    change_due: Decimal
    cart: PosCart


async def checkout(
    cart_id: uuid.UUID,
    *,
    payment_method: str,
    tendered_amount: Decimal | str | int | float,
    session: AsyncSession,
    actor: User,
    customer_id: uuid.UUID | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
    tax_amount: Decimal | str | int | float = Decimal("0"),
) -> CheckoutResult:
    """Convert the cart into a confirmed sale.

    Builds a ``SaleCreate``-shaped call to
    :func:`app.services.sales.create_draft` then calls
    :func:`app.services.sales.confirm` in the same transaction. Phase 6.3
    inventory + journal posting fires inside ``confirm`` — any failure
    rolls back the entire checkout, including the cart state flip.
    """
    cart = await _load(session, cart_id)
    _ensure_open(cart)
    if not cart.items:
        raise PosServiceError("cart has no items")

    if customer_id is not None:
        cart.customer_id = customer_id
    if customer_name is not None:
        cart.customer_name = customer_name
    if customer_email is not None:
        cart.customer_email = customer_email

    totals = compute_totals(cart)
    tendered = _q(tendered_amount)
    if tendered < totals.total:
        raise PosServiceError(
            f"tendered amount {tendered} less than total {totals.total + _q(tax_amount)}"
        )

    # Build sale items. Cart-level discount becomes the sale's
    # discount_amount; per-line discounts are folded into the line's
    # unit_price snapshot so the underlying SaleItem keeps its existing
    # (kind/product/quantity/unit_price) shape.
    sale_items: list[dict[str, Any]] = []
    for line in sorted(cart.items, key=lambda x: x.line_number):
        gross = _q(line.quantity * line.unit_price)
        disc = _line_discount_amount(line, gross)
        net = _q(gross - disc)
        effective_unit_price = _q(net / line.quantity) if line.quantity > 0 else Decimal("0")
        if line.product_id is not None:
            sale_items.append(
                {
                    "kind": "product",
                    "product_id": line.product_id,
                    "description": line.description,
                    "sku_or_job_number": line.sku,
                    "quantity": str(line.quantity),
                    "unit_price": str(effective_unit_price),
                }
            )
        else:
            sale_items.append(
                {
                    "kind": "manual",
                    "description": line.description,
                    "sku_or_job_number": line.sku,
                    "quantity": str(line.quantity),
                    "unit_price": str(effective_unit_price),
                }
            )

    customer_name_for_sale = (cart.customer_name or "POS Customer").strip() or "POS Customer"

    sale = await sales_service.create_draft(
        session,
        channel_id=cart.channel_id,
        external_order_id=None,
        customer_id=cart.customer_id,
        customer_name=customer_name_for_sale,
        customer_email=cart.customer_email,
        occurred_at=datetime.now(UTC),
        discount_amount=totals.cart_discount_amount,
        shipping_amount=Decimal("0"),
        tax_amount=_q(tax_amount),
        notes=f"POS cart {cart.id} ({payment_method})",
        items=sale_items,
        actor_user_id=actor.id,
    )
    sale = await sales_service.confirm(session, sale_id=sale.id, actor_user_id=actor.id)

    cart.state = PosCartState.CHECKED_OUT
    cart.sale_id = sale.id
    await session.flush()
    change_due = _q(tendered - (totals.total + _q(tax_amount)))
    if change_due < 0:
        change_due = Decimal("0")
    await _emit(
        session,
        event_type=sales_events.TYPE_POS_CART_CHECKED_OUT,
        cart_id=cart.id,
        payload={
            "cart_id": str(cart.id),
            "channel_id": str(cart.channel_id),
            "sale_id": str(sale.id),
            "sale_number": sale.sale_number,
            "total": str(_q(totals.total + _q(tax_amount))),
        },
        actor_user_id=actor.id,
    )
    cart = await _load(session, cart.id)
    return CheckoutResult(sale=sale, change_due=change_due, cart=cart)


async def void_cart(
    cart_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor: User | None,
) -> PosCart:
    cart = await _load(session, cart_id)
    _ensure_open(cart)
    cart.state = PosCartState.VOIDED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_POS_CART_VOIDED,
        cart_id=cart.id,
        payload={"cart_id": str(cart.id)},
        actor_user_id=actor.id if actor else None,
    )
    return await _load(session, cart.id)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, cart_id: uuid.UUID) -> PosCart:
    return await _load(session, cart_id)


__all__ = [
    "CheckoutResult",
    "PosBarcodeNotFoundError",
    "PosCartNotFoundError",
    "PosCartStateError",
    "PosChannelNotFoundError",
    "PosLineNotFoundError",
    "PosServiceError",
    "apply_discount",
    "checkout",
    "compute_totals",
    "get",
    "open_cart",
    "remove_line",
    "scan_barcode",
    "set_line_quantity",
    "void_cart",
]
