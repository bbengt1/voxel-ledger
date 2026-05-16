"""Quotes service (Phase 7.2, #110).

Owns the ``quote`` aggregate + its ``quote_item`` lines. Quote numbers
are allocated via the race-safe reference allocator with prefix ``QT``.

Totals math (Decimal-only, 6dp interior precision)::

    extended_amount = quantity * unit_price                 (per line)
    subtotal        = sum(extended_amount)
    total_amount    = subtotal - discount_amount + tax_amount

Quotes don't have a sales channel and don't post to the ledger, so there
is no channel-fee snapshot and no shipping component on the totals math.

State machine
-------------

    draft     -> sent       (send)
    draft     -> cancelled  (cancel)
    sent      -> accepted   (accept)
    sent      -> declined   (decline)
    sent      -> expired    (expire)
    sent      -> cancelled  (cancel)
    accepted  -> cancelled  (cancel) -- only before convert-to-invoice
    accepted  -> (terminal once an invoice has been created)
    declined  -> (terminal)
    expired   -> (terminal)
    cancelled -> (terminal)

``update_draft`` is only legal in ``draft``.

``convert_to_invoice`` is gated on Phase 7.3 (#111). Until that lands,
the service raises ``NotImplementedError`` with a clear pointer; the API
surfaces it as HTTP 501. The Phase 7.3 migration will (a) add the FK
constraint from ``quote.accepted_invoice_id`` -> ``invoice.id`` and (b)
replace the stub with the real implementation.
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

from app.events.types import ar as ar_events
from app.models.customer import Customer
from app.models.job import Job
from app.models.product import Product
from app.models.quote import Quote, QuoteItem, QuoteItemKind, QuoteState
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reference_number import ReferenceNumberService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class QuotesServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class QuoteNotFoundError(QuotesServiceError):
    """Mapped to 404."""


class CustomerNotFoundForQuoteError(QuotesServiceError):
    """The referenced customer doesn't exist."""


class InvalidQuoteItemError(QuotesServiceError):
    """Line failed validation (kind/ref mismatch, bad qty/price)."""


class InvalidQuoteStateError(QuotesServiceError):
    """Illegal state transition or write-while-not-draft."""


class InvalidCursorError(QuotesServiceError):
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
# State machine
# ---------------------------------------------------------------------------


_TRANSITIONS: dict[QuoteState, frozenset[QuoteState]] = {
    QuoteState.DRAFT: frozenset({QuoteState.SENT, QuoteState.CANCELLED}),
    QuoteState.SENT: frozenset(
        {
            QuoteState.ACCEPTED,
            QuoteState.DECLINED,
            QuoteState.EXPIRED,
            QuoteState.CANCELLED,
        }
    ),
    QuoteState.ACCEPTED: frozenset({QuoteState.CANCELLED}),
    QuoteState.DECLINED: frozenset(),
    QuoteState.EXPIRED: frozenset(),
    QuoteState.CANCELLED: frozenset(),
}


def _ensure_transition(current: QuoteState, target: QuoteState) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidQuoteStateError(
            f"cannot transition quote from {current.value} to {target.value}"
        )


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, quote_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(quote_id)}).encode("utf-8")
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
            aggregate_type=ar_events.AGGREGATE_TYPE_QUOTE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Item validation
# ---------------------------------------------------------------------------


def _coerce_kind(value: str | QuoteItemKind) -> QuoteItemKind:
    if isinstance(value, QuoteItemKind):
        return value
    try:
        return QuoteItemKind(value)
    except ValueError as exc:
        raise InvalidQuoteItemError(f"invalid item kind: {value!r}") from exc


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _coerce_kind(item.get("kind"))
    product_id = item.get("product_id")
    job_id = item.get("job_id")
    if isinstance(product_id, str):
        try:
            product_id = uuid.UUID(product_id)
        except ValueError as exc:
            raise InvalidQuoteItemError(f"invalid product_id: {product_id!r}") from exc
    if isinstance(job_id, str):
        try:
            job_id = uuid.UUID(job_id)
        except ValueError as exc:
            raise InvalidQuoteItemError(f"invalid job_id: {job_id!r}") from exc
    description = (item.get("description") or "").strip()
    sku_or_job_number = item.get("sku_or_job_number")

    if not description:
        raise InvalidQuoteItemError("item description is required")

    if kind == QuoteItemKind.PRODUCT:
        if product_id is None or job_id is not None:
            raise InvalidQuoteItemError("kind=product requires product_id and no job_id")
    elif kind == QuoteItemKind.JOB:
        if job_id is None or product_id is not None:
            raise InvalidQuoteItemError("kind=job requires job_id and no product_id")
    else:  # MANUAL
        if product_id is not None or job_id is not None:
            raise InvalidQuoteItemError("kind=manual requires both product_id and job_id be null")

    try:
        quantity = _q(item.get("quantity", "1"))
        unit_price = _q(item.get("unit_price", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidQuoteItemError(f"invalid numeric value on item: {exc}") from exc

    if quantity <= 0:
        raise InvalidQuoteItemError("quantity must be positive")
    if unit_price < 0:
        raise InvalidQuoteItemError("unit_price must be non-negative")

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
    product_ids = {i["product_id"] for i in items if i["product_id"] is not None}
    job_ids = {i["job_id"] for i in items if i["job_id"] is not None}

    for pid in product_ids:
        ok = (await session.execute(select(exists().where(Product.id == pid)))).scalar_one()
        if not ok:
            raise InvalidQuoteItemError(f"product {pid} not found")
    for jid in job_ids:
        ok = (await session.execute(select(exists().where(Job.id == jid)))).scalar_one()
        if not ok:
            raise InvalidQuoteItemError(f"job {jid} not found")


# ---------------------------------------------------------------------------
# Totals computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Totals:
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


def _compute_totals(
    *,
    items: list[dict[str, Any]],
    discount_amount: Decimal,
    tax_amount: Decimal,
) -> _Totals:
    subtotal = Decimal("0")
    for item in items:
        ext = _q(item["quantity"] * item["unit_price"])
        item["extended_amount"] = ext
        subtotal += ext
    subtotal = _q(subtotal)
    discount = _q(discount_amount)
    tax = _q(tax_amount)
    total = _q(subtotal - discount + tax)
    return _Totals(
        subtotal=subtotal,
        discount_amount=discount,
        tax_amount=tax,
        total_amount=total,
    )


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, quote_id: uuid.UUID, *, with_items: bool = True) -> Quote:
    stmt = select(Quote).where(Quote.id == quote_id)
    if with_items:
        stmt = stmt.options(selectinload(Quote.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise QuoteNotFoundError(str(quote_id))
    if with_items:
        await session.refresh(row, ["items"])
    return row


async def _load_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    stmt = select(Customer).where(Customer.id == customer_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CustomerNotFoundForQuoteError(str(customer_id))
    return row


def _payload_items(items: list[QuoteItem]) -> list[dict[str, Any]]:
    return [
        {
            "line_number": i.line_number,
            "kind": i.kind.value if isinstance(i.kind, QuoteItemKind) else i.kind,
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


def _created_payload(quote: Quote) -> dict[str, Any]:
    return {
        "quote_id": str(quote.id),
        "quote_number": quote.quote_number,
        "customer_id": str(quote.customer_id),
        "state": quote.state.value,
        "issued_at": quote.issued_at.isoformat() if quote.issued_at else None,
        "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
        "subtotal": str(quote.subtotal),
        "discount_amount": str(quote.discount_amount),
        "tax_amount": str(quote.tax_amount),
        "total_amount": str(quote.total_amount),
        "notes": quote.notes,
        "billing_address_snapshot": quote.billing_address_snapshot,
        "items": _payload_items(quote.items),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    valid_until: datetime | None = None,
    discount_amount: Decimal | str | int | float = Decimal("0"),
    tax_amount: Decimal | str | int | float = Decimal("0"),
    notes: str | None = None,
    items: list[dict[str, Any]] | None = None,
    actor_user_id: uuid.UUID,
) -> Quote:
    """Allocate ``QT-YYYY-NNNN`` and create a draft quote.

    Snapshots the customer's billing_address onto the quote so later
    customer edits don't rewrite a sent quote's address.
    """
    customer = await _load_customer(session, customer_id)

    normalized_items: list[dict[str, Any]] = []
    for raw in items or []:
        normalized_items.append(_validate_item(raw))
    await _verify_item_refs(session, normalized_items)

    totals = _compute_totals(
        items=normalized_items,
        discount_amount=_q(discount_amount),
        tax_amount=_q(tax_amount),
    )

    quote_number = await ReferenceNumberService.allocate("QT", session=session)

    billing_snapshot = (
        dict(customer.billing_address) if customer.billing_address is not None else None
    )

    quote = Quote(
        quote_number=quote_number,
        customer_id=customer_id,
        state=QuoteState.DRAFT,
        valid_until=valid_until,
        subtotal=totals.subtotal,
        discount_amount=totals.discount_amount,
        tax_amount=totals.tax_amount,
        total_amount=totals.total_amount,
        notes=notes,
        billing_address_snapshot=billing_snapshot,
        created_by_user_id=actor_user_id,
    )
    session.add(quote)
    await session.flush()

    for idx, item in enumerate(normalized_items, start=1):
        session.add(
            QuoteItem(
                quote_id=quote.id,
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
        raise InvalidQuoteItemError(f"quote item integrity violation: {exc.orig}") from exc

    quote = await _load(session, quote.id)

    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_CREATED,
        aggregate_id=quote.id,
        payload=_created_payload(quote),
        actor_user_id=actor_user_id,
    )
    return quote


_EDITABLE_SCALAR_FIELDS = (
    "customer_id",
    "valid_until",
    "discount_amount",
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
    quote_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Quote:
    quote = await _load(session, quote_id)
    if quote.state != QuoteState.DRAFT:
        raise InvalidQuoteStateError(
            f"quote {quote_id} is in state {quote.state.value}; only draft quotes can be edited"
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_SCALAR_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("discount_amount", "tax_amount") and new_value is not None:
            new_value = _q(new_value)
        if field == "customer_id" and new_value is not None:
            # Verify FK + re-snapshot billing address.
            new_customer = await _load_customer(session, new_value)
            quote.billing_address_snapshot = (
                dict(new_customer.billing_address)
                if new_customer.billing_address is not None
                else None
            )
        current = getattr(quote, field)
        if isinstance(current, Decimal) and isinstance(new_value, Decimal):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(quote, field, new_value)

    items_changed = False
    if "items" in patch and patch["items"] is not None:
        items_changed = True
        normalized_items = [_validate_item(raw) for raw in patch["items"]]
        await _verify_item_refs(session, normalized_items)
        for item in normalized_items:
            item["extended_amount"] = _q(item["quantity"] * item["unit_price"])
        before["items"] = _payload_items(quote.items)
        for existing in list(quote.items):
            await session.delete(existing)
        await session.flush()
        quote.items.clear()
        for idx, item in enumerate(normalized_items, start=1):
            session.add(
                QuoteItem(
                    quote_id=quote.id,
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
            raise InvalidQuoteItemError(f"quote item integrity violation: {exc.orig}") from exc

    if not before and not items_changed:
        return quote

    # Replay totals.
    quote = await _load(session, quote.id)
    line_dicts = [
        {"quantity": line.quantity, "unit_price": line.unit_price} for line in quote.items
    ]
    totals = _compute_totals(
        items=line_dicts,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
    )
    quote.subtotal = totals.subtotal
    quote.discount_amount = totals.discount_amount
    quote.tax_amount = totals.tax_amount
    quote.total_amount = totals.total_amount
    after["totals"] = {
        "subtotal": str(totals.subtotal),
        "discount_amount": str(totals.discount_amount),
        "tax_amount": str(totals.tax_amount),
        "total_amount": str(totals.total_amount),
    }
    if items_changed:
        after["items"] = _payload_items(quote.items)

    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_UPDATED,
        aggregate_id=quote.id,
        payload={
            "quote_id": str(quote.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return quote


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def send(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Quote:
    """Move ``draft → sent`` and stamp ``issued_at``.

    Phase 7.7 (#TBD) will add an email worker that consumes
    ``ar.QuoteSent`` and dispatches the quote PDF; this service just
    emits the event.
    """
    quote = await _load(session, quote_id)
    _ensure_transition(quote.state, QuoteState.SENT)
    quote.state = QuoteState.SENT
    quote.issued_at = datetime.now(UTC)
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_SENT,
        aggregate_id=quote.id,
        payload={
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "customer_id": str(quote.customer_id),
            "total_amount": str(quote.total_amount),
            "issued_at": quote.issued_at.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    return quote


async def accept(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Quote:
    quote = await _load(session, quote_id)
    _ensure_transition(quote.state, QuoteState.ACCEPTED)
    quote.state = QuoteState.ACCEPTED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_ACCEPTED,
        aggregate_id=quote.id,
        payload={
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "customer_id": str(quote.customer_id),
            "total_amount": str(quote.total_amount),
        },
        actor_user_id=actor_user_id,
    )
    return quote


async def decline(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Quote:
    quote = await _load(session, quote_id)
    _ensure_transition(quote.state, QuoteState.DECLINED)
    quote.state = QuoteState.DECLINED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_DECLINED,
        aggregate_id=quote.id,
        payload={
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "customer_id": str(quote.customer_id),
        },
        actor_user_id=actor_user_id,
    )
    return quote


async def expire(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Quote:
    """Manual ``sent → expired`` transition. Phase 7.5/7.6 will add a
    sweeper that calls this once ``valid_until < now()``."""
    quote = await _load(session, quote_id)
    _ensure_transition(quote.state, QuoteState.EXPIRED)
    quote.state = QuoteState.EXPIRED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_EXPIRED,
        aggregate_id=quote.id,
        payload={
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "customer_id": str(quote.customer_id),
        },
        actor_user_id=actor_user_id,
    )
    return quote


async def cancel(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Quote:
    quote = await _load(session, quote_id)
    _ensure_transition(quote.state, QuoteState.CANCELLED)
    quote.state = QuoteState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_QUOTE_CANCELLED,
        aggregate_id=quote.id,
        payload={
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "customer_id": str(quote.customer_id),
        },
        actor_user_id=actor_user_id,
    )
    return quote


async def convert_to_invoice(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> uuid.UUID:
    """Convert an ``accepted`` quote into an invoice.

    Phase 7.2 ships the seam — the state column, ``accepted_invoice_id``
    column, and the route — but the real implementation depends on the
    Phase 7.3 invoice service. Until 7.3 lands, this raises
    ``NotImplementedError``; the API translates it to HTTP 501.
    """
    # Pre-flight: still load the quote so the caller gets a 404 first if
    # the quote id doesn't exist, before the not-implemented stub fires.
    await _load(session, quote_id, with_items=False)
    raise NotImplementedError(
        "convert_to_invoice requires Phase 7.3 (#111) invoice service; "
        "the seam (column + state machine) is in place but the implementation "
        "lands with Phase 7.3."
    )


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(
    session: AsyncSession,
    quote_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> Quote:
    return await _load(session, quote_id, with_items=with_items)


@dataclass
class QuotePage:
    items: list[Quote]
    next_cursor: str | None


async def list_quotes(
    session: AsyncSession,
    *,
    state: str | None = None,
    customer_id: uuid.UUID | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> QuotePage:
    stmt = select(Quote).options(selectinload(Quote.items))
    if state is not None:
        try:
            stmt = stmt.where(Quote.state == QuoteState(state))
        except ValueError as exc:
            raise QuotesServiceError(f"invalid state filter: {state!r}") from exc
    if customer_id is not None:
        stmt = stmt.where(Quote.customer_id == customer_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Quote.quote_number.ilike(like))
    if date_from is not None:
        stmt = stmt.where(Quote.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Quote.created_at <= date_to)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Quote.created_at < anchor_ts,
                and_(Quote.created_at == anchor_ts, Quote.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Quote.created_at), desc(Quote.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return QuotePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "CustomerNotFoundForQuoteError",
    "InvalidCursorError",
    "InvalidQuoteItemError",
    "InvalidQuoteStateError",
    "QuoteNotFoundError",
    "QuotePage",
    "QuotesServiceError",
    "accept",
    "cancel",
    "convert_to_invoice",
    "create_draft",
    "decline",
    "expire",
    "get",
    "list_quotes",
    "send",
    "update_draft",
]
