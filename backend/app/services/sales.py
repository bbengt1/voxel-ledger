"""Sales service (Phase 6.2, #94).

Owns the ``sale`` aggregate + its ``sale_item`` lines. Sale numbers are
allocated via the race-safe reference allocator with prefix ``SO``.

Totals math (Decimal-only, 6dp interior precision):

    extended_amount = quantity * unit_price                     (per line)
    subtotal        = sum(extended_amount)
    channel_fee     = SalesChannelService.compute_fee(
                          channel,
                          subtotal - discount + shipping)         (snapshot)
    total_amount    = subtotal - discount + shipping + tax

The channel fee is NOT subtracted from ``total_amount`` — it's an
operator-side expense, not a customer-facing discount. The snapshot is
taken at create/update time and NOT recomputed at confirm/fulfill, so
later channel-fee model changes don't rewrite already-confirmed sales.

State machine:

    draft     -> confirmed   (confirm)
    draft     -> cancelled   (cancel)
    confirmed -> fulfilled   (fulfill)
    confirmed -> cancelled   (cancel)
    fulfilled -> (terminal)
    cancelled -> (terminal)

``update_draft`` is only legal in ``draft`` — once confirmed, edits are
out of scope until Phase 6.3 lands the post-confirm correction flow.

Item kind invariant
-------------------
Exactly one of (``product_id``, ``job_id``) is set, OR both are null for
``kind=manual``. Both the service and a DB CHECK constraint enforce
this; the service raises ``InvalidSaleItemError`` ahead of the DB so
callers get a clean 400 instead of an IntegrityError.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import sales as sales_events
from app.models.job import Job
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleItemKind, SaleState
from app.models.sales_channel import SalesChannel
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.cogs import service as cogs_service
from app.services.reference_number import ReferenceNumberService
from app.services.sales_channels import compute_fee

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SalesServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class SaleNotFoundError(SalesServiceError):
    """Mapped to 404."""


class SalesChannelNotFoundError(SalesServiceError):
    """Channel id referenced by the sale doesn't exist."""


class InvalidSaleItemError(SalesServiceError):
    """Line failed validation (kind/ref mismatch, bad qty/price)."""


class InvalidSaleStateError(SalesServiceError):
    """Illegal state transition or write-while-confirmed."""


class InvalidCursorError(SalesServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")  # 6dp interior precision.


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_TRANSITIONS: dict[SaleState, frozenset[SaleState]] = {
    SaleState.DRAFT: frozenset({SaleState.CONFIRMED, SaleState.CANCELLED}),
    SaleState.CONFIRMED: frozenset({SaleState.FULFILLED, SaleState.CANCELLED}),
    SaleState.FULFILLED: frozenset(),
    SaleState.CANCELLED: frozenset(),
}


def _ensure_transition(current: SaleState, target: SaleState) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidSaleStateError(
            f"cannot transition sale from {current.value} to {target.value}"
        )


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, sale_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(sale_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Event emission helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=sales_events.AGGREGATE_TYPE_SALE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Item validation + line math
# ---------------------------------------------------------------------------


def _coerce_kind(value: str | SaleItemKind) -> SaleItemKind:
    if isinstance(value, SaleItemKind):
        return value
    try:
        return SaleItemKind(value)
    except ValueError as exc:
        raise InvalidSaleItemError(f"invalid item kind: {value!r}") from exc


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one line. Enforces the kind/ref invariant + numeric coercion.

    Returns a dict with normalized values; raises ``InvalidSaleItemError``
    on any violation. Does NOT compute ``extended_amount`` — that happens
    when lines are assembled into the sale so the caller can stamp
    ``line_number`` first.
    """
    kind = _coerce_kind(item.get("kind"))
    product_id = item.get("product_id")
    job_id = item.get("job_id")
    if isinstance(product_id, str):
        try:
            product_id = uuid.UUID(product_id)
        except ValueError as exc:
            raise InvalidSaleItemError(f"invalid product_id: {product_id!r}") from exc
    if isinstance(job_id, str):
        try:
            job_id = uuid.UUID(job_id)
        except ValueError as exc:
            raise InvalidSaleItemError(f"invalid job_id: {job_id!r}") from exc
    description = (item.get("description") or "").strip()
    sku_or_job_number = item.get("sku_or_job_number")

    if not description:
        raise InvalidSaleItemError("item description is required")

    if kind == SaleItemKind.PRODUCT:
        if product_id is None or job_id is not None:
            raise InvalidSaleItemError("kind=product requires product_id and no job_id")
    elif kind == SaleItemKind.JOB:
        if job_id is None or product_id is not None:
            raise InvalidSaleItemError("kind=job requires job_id and no product_id")
    else:  # MANUAL
        if product_id is not None or job_id is not None:
            raise InvalidSaleItemError("kind=manual requires both product_id and job_id be null")

    try:
        quantity = _q(item.get("quantity", "1"))
        unit_price = _q(item.get("unit_price", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidSaleItemError(f"invalid numeric value on item: {exc}") from exc

    if quantity <= 0:
        raise InvalidSaleItemError("quantity must be positive")
    if unit_price < 0:
        raise InvalidSaleItemError("unit_price must be non-negative")

    return {
        "kind": kind,
        "product_id": product_id,
        "job_id": job_id,
        "description": description,
        "sku_or_job_number": sku_or_job_number,
        "quantity": quantity,
        "unit_price": unit_price,
    }


async def _verify_item_refs(session: AsyncSession, items: list[dict[str, Any]]) -> None:
    """Ensure each product_id/job_id actually exists. Cheaper than waiting
    for an FK violation since the error message can be specific."""
    product_ids = {i["product_id"] for i in items if i["product_id"] is not None}
    job_ids = {i["job_id"] for i in items if i["job_id"] is not None}

    for pid in product_ids:
        ok = (await session.execute(select(exists().where(Product.id == pid)))).scalar_one()
        if not ok:
            raise InvalidSaleItemError(f"product {pid} not found")
    for jid in job_ids:
        ok = (await session.execute(select(exists().where(Job.id == jid)))).scalar_one()
        if not ok:
            raise InvalidSaleItemError(f"job {jid} not found")


# ---------------------------------------------------------------------------
# Totals computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Totals:
    subtotal: Decimal
    discount_amount: Decimal
    shipping_amount: Decimal
    tax_amount: Decimal
    channel_fee_amount: Decimal
    total_amount: Decimal


def _compute_totals(
    *,
    channel: SalesChannel,
    items: list[dict[str, Any]],
    discount_amount: Decimal,
    shipping_amount: Decimal,
    tax_amount: Decimal,
) -> _Totals:
    subtotal = Decimal("0")
    for item in items:
        ext = _q(item["quantity"] * item["unit_price"])
        item["extended_amount"] = ext
        subtotal += ext
    subtotal = _q(subtotal)
    discount = _q(discount_amount)
    shipping = _q(shipping_amount)
    tax = _q(tax_amount)

    fee_gross = subtotal - discount + shipping
    channel_fee = _q(compute_fee(channel, fee_gross))

    total = _q(subtotal - discount + shipping + tax)

    return _Totals(
        subtotal=subtotal,
        discount_amount=discount,
        shipping_amount=shipping,
        tax_amount=tax,
        channel_fee_amount=channel_fee,
        total_amount=total,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, sale_id: uuid.UUID, *, with_items: bool = True) -> Sale:
    stmt = select(Sale).where(Sale.id == sale_id)
    if with_items:
        stmt = stmt.options(selectinload(Sale.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SaleNotFoundError(str(sale_id))
    if with_items:
        await session.refresh(row, ["items"])
    return row


async def _load_channel(session: AsyncSession, channel_id: uuid.UUID) -> SalesChannel:
    stmt = select(SalesChannel).where(SalesChannel.id == channel_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SalesChannelNotFoundError(str(channel_id))
    return row


def _payload_items(items: list[SaleItem]) -> list[dict[str, Any]]:
    return [
        {
            "line_number": i.line_number,
            "kind": i.kind.value if isinstance(i.kind, SaleItemKind) else i.kind,
            "product_id": str(i.product_id) if i.product_id else None,
            "job_id": str(i.job_id) if i.job_id else None,
            "description": i.description,
            "sku_or_job_number": i.sku_or_job_number,
            "quantity": str(i.quantity),
            "unit_price": str(i.unit_price),
            "extended_amount": str(i.extended_amount),
        }
        for i in sorted(items, key=lambda x: x.line_number)
    ]


def _created_payload(sale: Sale) -> dict[str, Any]:
    return {
        "sale_id": str(sale.id),
        "sale_number": sale.sale_number,
        "channel_id": str(sale.channel_id),
        "external_order_id": sale.external_order_id,
        "customer_id": str(sale.customer_id) if sale.customer_id else None,
        "customer_name": sale.customer_name,
        "customer_email": sale.customer_email,
        "occurred_at": sale.occurred_at.isoformat(),
        "subtotal": str(sale.subtotal),
        "discount_amount": str(sale.discount_amount),
        "shipping_amount": str(sale.shipping_amount),
        "tax_amount": str(sale.tax_amount),
        "channel_fee_amount": str(sale.channel_fee_amount),
        "total_amount": str(sale.total_amount),
        "state": sale.state.value,
        "notes": sale.notes,
        "items": _payload_items(sale.items),
    }


async def create_draft(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    external_order_id: str | None,
    customer_id: uuid.UUID | None = None,
    customer_name: str,
    customer_email: str | None,
    occurred_at: datetime,
    discount_amount: Decimal | str | int | float = Decimal("0"),
    shipping_amount: Decimal | str | int | float = Decimal("0"),
    tax_amount: Decimal | str | int | float = Decimal("0"),
    notes: str | None = None,
    items: list[dict[str, Any]] | None = None,
    actor_user_id: uuid.UUID,
) -> Sale:
    """Allocate ``SO-YYYY-NNNN`` and create a draft sale.

    All numeric inputs accept Decimal/str/int/float; interior math stays
    in Decimal. Totals are computed + the channel fee is snapshotted
    here.
    """
    customer_name = (customer_name or "").strip()
    if not customer_name:
        raise SalesServiceError("customer_name is required")

    channel = await _load_channel(session, channel_id)

    normalized_items: list[dict[str, Any]] = []
    for raw in items or []:
        normalized_items.append(_validate_item(raw))
    await _verify_item_refs(session, normalized_items)

    totals = _compute_totals(
        channel=channel,
        items=normalized_items,
        discount_amount=_q(discount_amount),
        shipping_amount=_q(shipping_amount),
        tax_amount=_q(tax_amount),
    )

    sale_number = await ReferenceNumberService.allocate("SO", session=session)

    sale = Sale(
        sale_number=sale_number,
        channel_id=channel_id,
        external_order_id=external_order_id,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_email=customer_email,
        occurred_at=occurred_at,
        subtotal=totals.subtotal,
        discount_amount=totals.discount_amount,
        shipping_amount=totals.shipping_amount,
        tax_amount=totals.tax_amount,
        channel_fee_amount=totals.channel_fee_amount,
        total_amount=totals.total_amount,
        state=SaleState.DRAFT,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(sale)
    await session.flush()

    for idx, item in enumerate(normalized_items, start=1):
        session.add(
            SaleItem(
                sale_id=sale.id,
                line_number=idx,
                kind=item["kind"],
                product_id=item["product_id"],
                job_id=item["job_id"],
                description=item["description"],
                sku_or_job_number=item["sku_or_job_number"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                extended_amount=item["extended_amount"],
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidSaleItemError(f"sale item integrity violation: {exc.orig}") from exc

    sale = await _load(session, sale.id)

    await _emit(
        session,
        event_type=sales_events.TYPE_SALE_CREATED,
        aggregate_id=sale.id,
        payload=_created_payload(sale),
        actor_user_id=actor_user_id,
    )
    return sale


_EDITABLE_SCALAR_FIELDS = (
    "channel_id",
    "external_order_id",
    "customer_id",
    "customer_name",
    "customer_email",
    "occurred_at",
    "discount_amount",
    "shipping_amount",
    "tax_amount",
    "notes",
)


def _serialize_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def update_draft(
    session: AsyncSession,
    *,
    sale_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Sale:
    sale = await _load(session, sale_id)
    if sale.state != SaleState.DRAFT:
        raise InvalidSaleStateError(
            f"sale {sale_id} is in state {sale.state.value}; only draft sales can be edited"
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    # Scalar field merge.
    for field in _EDITABLE_SCALAR_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("discount_amount", "shipping_amount", "tax_amount") and new_value is not None:
            new_value = _q(new_value)
        if field == "customer_name" and new_value is not None:
            new_value = new_value.strip()
            if not new_value:
                raise SalesServiceError("customer_name must not be empty")
        current = getattr(sale, field)
        if isinstance(current, Decimal) and isinstance(new_value, Decimal):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(sale, field, new_value)

    items_changed = False
    if "items" in patch and patch["items"] is not None:
        items_changed = True
        normalized_items = [_validate_item(raw) for raw in patch["items"]]
        await _verify_item_refs(session, normalized_items)
        # Stamp ``extended_amount`` on each line so the insert below has
        # the column populated. ``_compute_totals`` runs later for the
        # rolled-up sale totals (with discount/shipping/tax applied).
        for item in normalized_items:
            item["extended_amount"] = _q(item["quantity"] * item["unit_price"])
        before["items"] = _payload_items(sale.items)
        # Clear existing — cascade-delete via SQLAlchemy.
        for existing in list(sale.items):
            await session.delete(existing)
        await session.flush()
        sale.items.clear()
        for idx, item in enumerate(normalized_items, start=1):
            session.add(
                SaleItem(
                    sale_id=sale.id,
                    line_number=idx,
                    kind=item["kind"],
                    product_id=item["product_id"],
                    job_id=item["job_id"],
                    description=item["description"],
                    sku_or_job_number=item["sku_or_job_number"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    extended_amount=item["extended_amount"],
                )
            )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise InvalidSaleItemError(f"sale item integrity violation: {exc.orig}") from exc

    if not before and not items_changed:
        return sale

    # Replay totals — uses the (possibly updated) channel + line set.
    sale = await _load(session, sale.id)
    channel = await _load_channel(session, sale.channel_id)

    line_dicts: list[dict[str, Any]] = []
    for line in sale.items:
        line_dicts.append(
            {
                "quantity": line.quantity,
                "unit_price": line.unit_price,
            }
        )
    totals = _compute_totals(
        channel=channel,
        items=line_dicts,
        discount_amount=sale.discount_amount,
        shipping_amount=sale.shipping_amount,
        tax_amount=sale.tax_amount,
    )
    sale.subtotal = totals.subtotal
    sale.discount_amount = totals.discount_amount
    sale.shipping_amount = totals.shipping_amount
    sale.tax_amount = totals.tax_amount
    sale.channel_fee_amount = totals.channel_fee_amount
    sale.total_amount = totals.total_amount
    after["totals"] = {
        "subtotal": str(totals.subtotal),
        "discount_amount": str(totals.discount_amount),
        "shipping_amount": str(totals.shipping_amount),
        "tax_amount": str(totals.tax_amount),
        "channel_fee_amount": str(totals.channel_fee_amount),
        "total_amount": str(totals.total_amount),
    }
    if items_changed:
        after["items"] = _payload_items(sale.items)

    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_SALE_UPDATED,
        aggregate_id=sale.id,
        payload={
            "sale_id": str(sale.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return sale


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def confirm(
    session: AsyncSession,
    *,
    sale_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Sale:
    """Confirm a draft sale and post inventory + journal entries.

    Atomicity invariant (Phase 6.3, #95): the state flip, the
    ``SaleConfirmed`` event, the COGS service's inventory transactions,
    the journal entry post, and the ``SalePosted`` event all live in
    the caller's transaction. Any raise rolls back everything — there
    is no partial confirm.
    """
    sale = await _load(session, sale_id)
    _ensure_transition(sale.state, SaleState.CONFIRMED)
    sale.state = SaleState.CONFIRMED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SALE_CONFIRMED,
        aggregate_id=sale.id,
        payload={
            "sale_id": str(sale.id),
            "sale_number": sale.sale_number,
            "channel_id": str(sale.channel_id),
            "total_amount": str(sale.total_amount),
        },
        actor_user_id=actor_user_id,
    )
    # Same-TX side effects: inventory transactions, journal entry,
    # SalePosted audit event. If any of these raises, the router's
    # ``rollback()`` discards EVERYTHING above this line too — that's
    # the keystone invariant.
    await cogs_service.post_for_sale(sale.id, session=session, actor_user_id=actor_user_id)
    return sale


async def fulfill(
    session: AsyncSession,
    *,
    sale_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Sale:
    sale = await _load(session, sale_id)
    _ensure_transition(sale.state, SaleState.FULFILLED)
    sale.state = SaleState.FULFILLED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SALE_FULFILLED,
        aggregate_id=sale.id,
        payload={"sale_id": str(sale.id), "sale_number": sale.sale_number},
        actor_user_id=actor_user_id,
    )
    return sale


async def cancel(
    session: AsyncSession,
    *,
    sale_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Sale:
    """Cancel a sale.

    If the sale was previously confirmed, the COGS service reverses
    the inventory + journal-entry posting in the same transaction.
    Cancelling from ``draft`` is a no-op on the side-effect side
    (nothing was posted yet); the SaleCancelled event still fires.
    """
    sale = await _load(session, sale_id)
    was_confirmed = sale.state == SaleState.CONFIRMED
    _ensure_transition(sale.state, SaleState.CANCELLED)
    sale.state = SaleState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SALE_CANCELLED,
        aggregate_id=sale.id,
        payload={"sale_id": str(sale.id), "sale_number": sale.sale_number},
        actor_user_id=actor_user_id,
    )
    if was_confirmed:
        await cogs_service.reverse_for_sale(sale.id, session=session, actor_user_id=actor_user_id)
    return sale


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(
    session: AsyncSession,
    sale_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> Sale:
    return await _load(session, sale_id, with_items=with_items)


@dataclass
class SalePage:
    items: list[Sale]
    next_cursor: str | None


async def list_sales(
    session: AsyncSession,
    *,
    state: str | None = None,
    channel_id: uuid.UUID | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> SalePage:
    stmt = select(Sale).options(selectinload(Sale.items))
    if state is not None:
        try:
            stmt = stmt.where(Sale.state == SaleState(state))
        except ValueError as exc:
            raise SalesServiceError(f"invalid state filter: {state!r}") from exc
    if channel_id is not None:
        stmt = stmt.where(Sale.channel_id == channel_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Sale.sale_number.ilike(like),
                Sale.customer_name.ilike(like),
                Sale.external_order_id.ilike(like),
            )
        )
    if date_from is not None:
        stmt = stmt.where(Sale.occurred_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Sale.occurred_at <= date_to)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Sale.created_at < anchor_ts,
                and_(Sale.created_at == anchor_ts, Sale.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Sale.created_at), desc(Sale.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return SalePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidCursorError",
    "InvalidSaleItemError",
    "InvalidSaleStateError",
    "SaleNotFoundError",
    "SalePage",
    "SalesChannelNotFoundError",
    "SalesServiceError",
    "cancel",
    "confirm",
    "create_draft",
    "fulfill",
    "get",
    "list_sales",
    "update_draft",
]
