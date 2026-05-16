"""Invoices service (Phase 7.3, #111).

The invoice is the AR system-of-record. Issuing an invoice
(``draft -> issued``) posts to the GL atomically INSIDE THE SAME DB
TRANSACTION as the state flip. This same-TX invariant is the keystone
v2 rule for AR (mirrors Phase 6.3 COGS): if any step (re-snapshot,
account resolve, JE post, event emit) raises, the outer transaction
rolls back and NOTHING persists — not the state flip, not the JE, not
the audit events. Do not introduce nested commits.

Account resolution at issue time
--------------------------------
* AR debit account: ``CustomersService.resolve_default_ar_account``
  (customer.default_ar_account_id -> settings
  ``sales_posting.default_ar_account_id`` -> settings
  ``ar.default_ar_account_id``).
* Revenue credit account: per-line override (not implemented today —
  products/jobs don't carry a revenue_account_id column yet) -> customer
  default -> settings ``ar.default_revenue_account_id``. Falls through
  to the legacy ``sales_posting.default_ar_account_id`` only as a last
  resort to keep tests working on dev installs that only configured the
  Phase 6.3 keys.
* Sales tax payable credit (when ``tax_amount > 0``): settings
  ``ar.default_sales_tax_payable_account_id`` -> settings
  ``sales_posting.sales_tax_payable_account_id``.

``create_from_sale`` rationale (stub)
-------------------------------------
Phase 6.3's sale-confirm flow already debits AR and credits Revenue.
Issuing a SECOND invoice for the same sale would double-count revenue.
The clean fix is an ``AR Pending`` clearing account: the sale's confirm
debits AR-Pending instead of AR-Real-Customer, and the invoice's issue
moves AR-Pending -> AR-Real-Customer (revenue is left alone where the
sale put it). Designing the clearing-account dance is Phase 9 work; for
now ``create_from_sale`` raises ``NotImplementedError`` with a pointer.

Quote conversion
----------------
``create_from_quote`` copies line items from an accepted quote into a
fresh draft invoice and sets ``invoice.quote_id`` to the source. The
caller (``quotes.convert_to_invoice``) stamps
``quote.accepted_invoice_id = invoice.id`` and emits
``ar.QuoteConvertedToInvoice``.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ar as ar_events
from app.models.customer import Customer
from app.models.invoice import (
    Invoice,
    InvoiceItem,
    InvoiceItemKind,
    InvoiceState,
)
from app.models.job import Job
from app.models.journal_entry import JournalEntry
from app.models.product import Product
from app.models.quote import Quote, QuoteItemKind
from app.schemas.events import EventCreate
from app.services import customers as customers_service
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvoiceServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class InvoiceNotFoundError(InvoiceServiceError):
    """Mapped to 404."""


class CustomerNotFoundForInvoiceError(InvoiceServiceError):
    """The referenced customer doesn't exist."""


class InvalidInvoiceItemError(InvoiceServiceError):
    """Line failed validation (kind/ref mismatch, bad qty/price)."""


class InvalidInvoiceStateError(InvoiceServiceError):
    """Illegal state transition or write-while-not-draft."""


class MissingArPostingAccountError(InvoiceServiceError):
    """Required AR posting account setting (or fallback chain) isn't set.

    Mapped to 400 with a clear "configure default AR posting accounts"
    message — the operator needs to set the GL account IDs via the
    settings endpoint before any invoice can issue.
    """


class InvoiceHasPaymentsError(InvoiceServiceError):
    """Voiding an invoice that already has payments applied is illegal
    until Phase 7.4 lands the unapply flow."""


class InvalidCursorError(InvoiceServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_TRANSITIONS: dict[InvoiceState, frozenset[InvoiceState]] = {
    InvoiceState.DRAFT: frozenset({InvoiceState.ISSUED, InvoiceState.VOID}),
    InvoiceState.ISSUED: frozenset(
        {
            InvoiceState.PARTIALLY_PAID,
            InvoiceState.PAID,
            InvoiceState.OVERDUE,
            InvoiceState.VOID,
        }
    ),
    InvoiceState.PARTIALLY_PAID: frozenset(
        {InvoiceState.PAID, InvoiceState.OVERDUE, InvoiceState.VOID}
    ),
    InvoiceState.OVERDUE: frozenset(
        {InvoiceState.PARTIALLY_PAID, InvoiceState.PAID, InvoiceState.VOID}
    ),
    InvoiceState.PAID: frozenset(),
    InvoiceState.VOID: frozenset(),
}


def _ensure_transition(current: InvoiceState, target: InvoiceState) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidInvoiceStateError(
            f"cannot transition invoice from {current.value} to {target.value}"
        )


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, invoice_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(invoice_id)}).encode("utf-8")
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
            aggregate_type=ar_events.AGGREGATE_TYPE_INVOICE,
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


def _coerce_kind(value: str | InvoiceItemKind) -> InvoiceItemKind:
    if isinstance(value, InvoiceItemKind):
        return value
    try:
        return InvoiceItemKind(value)
    except ValueError as exc:
        raise InvalidInvoiceItemError(f"invalid item kind: {value!r}") from exc


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _coerce_kind(item.get("kind"))
    product_id = item.get("product_id")
    job_id = item.get("job_id")
    if isinstance(product_id, str):
        try:
            product_id = uuid.UUID(product_id)
        except ValueError as exc:
            raise InvalidInvoiceItemError(f"invalid product_id: {product_id!r}") from exc
    if isinstance(job_id, str):
        try:
            job_id = uuid.UUID(job_id)
        except ValueError as exc:
            raise InvalidInvoiceItemError(f"invalid job_id: {job_id!r}") from exc
    description = (item.get("description") or "").strip()
    sku_or_job_number = item.get("sku_or_job_number")

    if not description:
        raise InvalidInvoiceItemError("item description is required")

    if kind == InvoiceItemKind.PRODUCT:
        if product_id is None or job_id is not None:
            raise InvalidInvoiceItemError("kind=product requires product_id and no job_id")
    elif kind == InvoiceItemKind.JOB:
        if job_id is None or product_id is not None:
            raise InvalidInvoiceItemError("kind=job requires job_id and no product_id")
    else:  # MANUAL
        if product_id is not None or job_id is not None:
            raise InvalidInvoiceItemError("kind=manual requires both product_id and job_id be null")

    try:
        quantity = _q(item.get("quantity", "1"))
        unit_price = _q(item.get("unit_price", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidInvoiceItemError(f"invalid numeric value on item: {exc}") from exc

    if quantity <= 0:
        raise InvalidInvoiceItemError("quantity must be positive")
    if unit_price < 0:
        raise InvalidInvoiceItemError("unit_price must be non-negative")

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
            raise InvalidInvoiceItemError(f"product {pid} not found")
    for jid in job_ids:
        ok = (await session.execute(select(exists().where(Job.id == jid)))).scalar_one()
        if not ok:
            raise InvalidInvoiceItemError(f"job {jid} not found")


# ---------------------------------------------------------------------------
# Totals
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


async def _load(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    if with_items:
        stmt = stmt.options(selectinload(Invoice.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise InvoiceNotFoundError(str(invoice_id))
    if with_items:
        await session.refresh(row, ["items"])
    return row


async def _load_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    stmt = select(Customer).where(Customer.id == customer_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CustomerNotFoundForInvoiceError(str(customer_id))
    return row


def _payload_items(items: list[InvoiceItem]) -> list[dict[str, Any]]:
    return [
        {
            "line_number": i.line_number,
            "kind": i.kind.value if isinstance(i.kind, InvoiceItemKind) else i.kind,
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


def _created_payload(invoice: Invoice) -> dict[str, Any]:
    return {
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "customer_id": str(invoice.customer_id),
        "quote_id": str(invoice.quote_id) if invoice.quote_id else None,
        "sale_id": str(invoice.sale_id) if invoice.sale_id else None,
        "state": invoice.state.value,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
        "subtotal": str(invoice.subtotal),
        "discount_amount": str(invoice.discount_amount),
        "tax_amount": str(invoice.tax_amount),
        "total_amount": str(invoice.total_amount),
        "currency": invoice.currency,
        "notes": invoice.notes,
        "billing_address_snapshot": invoice.billing_address_snapshot,
        "items": _payload_items(invoice.items),
    }


# ---------------------------------------------------------------------------
# CRUD: create / update draft
# ---------------------------------------------------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    due_at: datetime | None = None,
    discount_amount: Decimal | str | int | float = Decimal("0"),
    tax_amount: Decimal | str | int | float = Decimal("0"),
    notes: str | None = None,
    items: list[dict[str, Any]] | None = None,
    quote_id: uuid.UUID | None = None,
    sale_id: uuid.UUID | None = None,
    currency: str = "USD",
    actor_user_id: uuid.UUID,
) -> Invoice:
    """Allocate ``INV-YYYY-NNNN`` and create a draft invoice.

    Snapshots ``customer.billing_address`` onto the invoice so later
    edits of the customer don't rewrite an already-issued invoice's
    address. The tentative ``due_at`` (issued_at + payment_terms_days)
    is recomputed at issue time; if the caller supplies one here, it's
    stored as-is on the draft and will be re-computed at issue.
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

    invoice_number = await ReferenceNumberService.allocate("INV", session=session)

    billing_snapshot = (
        dict(customer.billing_address) if customer.billing_address is not None else None
    )

    # Tentative due_at if not supplied — set to now + payment_terms_days
    # so the draft has a sensible placeholder. Re-stamped at issue time.
    tentative_due_at = due_at
    if tentative_due_at is None and customer.payment_terms_days is not None:
        tentative_due_at = datetime.now(UTC) + timedelta(days=customer.payment_terms_days)

    invoice = Invoice(
        invoice_number=invoice_number,
        customer_id=customer_id,
        quote_id=quote_id,
        sale_id=sale_id,
        state=InvoiceState.DRAFT,
        due_at=tentative_due_at,
        subtotal=totals.subtotal,
        discount_amount=totals.discount_amount,
        tax_amount=totals.tax_amount,
        total_amount=totals.total_amount,
        amount_paid=_ZERO,
        amount_outstanding=totals.total_amount,
        currency=currency,
        notes=notes,
        billing_address_snapshot=billing_snapshot,
        created_by_user_id=actor_user_id,
    )
    session.add(invoice)
    await session.flush()

    for idx, item in enumerate(normalized_items, start=1):
        session.add(
            InvoiceItem(
                invoice_id=invoice.id,
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
        raise InvalidInvoiceItemError(f"invoice item integrity violation: {exc.orig}") from exc

    invoice = await _load(session, invoice.id)

    await _emit(
        session,
        event_type=ar_events.TYPE_INVOICE_CREATED,
        aggregate_id=invoice.id,
        payload=_created_payload(invoice),
        actor_user_id=actor_user_id,
    )
    return invoice


_EDITABLE_SCALAR_FIELDS = (
    "customer_id",
    "due_at",
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
    invoice_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Invoice:
    invoice = await _load(session, invoice_id)
    if invoice.state != InvoiceState.DRAFT:
        raise InvalidInvoiceStateError(
            f"invoice {invoice_id} is in state {invoice.state.value}; "
            "only draft invoices can be edited"
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
            new_customer = await _load_customer(session, new_value)
            invoice.billing_address_snapshot = (
                dict(new_customer.billing_address)
                if new_customer.billing_address is not None
                else None
            )
        current = getattr(invoice, field)
        if isinstance(current, Decimal) and isinstance(new_value, Decimal):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(invoice, field, new_value)

    items_changed = False
    if "items" in patch and patch["items"] is not None:
        items_changed = True
        normalized_items = [_validate_item(raw) for raw in patch["items"]]
        await _verify_item_refs(session, normalized_items)
        for item in normalized_items:
            item["extended_amount"] = _q(item["quantity"] * item["unit_price"])
        before["items"] = _payload_items(invoice.items)
        for existing in list(invoice.items):
            await session.delete(existing)
        await session.flush()
        invoice.items.clear()
        for idx, item in enumerate(normalized_items, start=1):
            session.add(
                InvoiceItem(
                    invoice_id=invoice.id,
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
            raise InvalidInvoiceItemError(f"invoice item integrity violation: {exc.orig}") from exc

    if not before and not items_changed:
        return invoice

    invoice = await _load(session, invoice.id)
    line_dicts = [
        {"quantity": line.quantity, "unit_price": line.unit_price} for line in invoice.items
    ]
    totals = _compute_totals(
        items=line_dicts,
        discount_amount=invoice.discount_amount,
        tax_amount=invoice.tax_amount,
    )
    invoice.subtotal = totals.subtotal
    invoice.discount_amount = totals.discount_amount
    invoice.tax_amount = totals.tax_amount
    invoice.total_amount = totals.total_amount
    invoice.amount_outstanding = _q(totals.total_amount - _q(invoice.amount_paid))
    after["totals"] = {
        "subtotal": str(totals.subtotal),
        "discount_amount": str(totals.discount_amount),
        "tax_amount": str(totals.tax_amount),
        "total_amount": str(totals.total_amount),
    }
    if items_changed:
        after["items"] = _payload_items(invoice.items)

    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_INVOICE_UPDATED,
        aggregate_id=invoice.id,
        payload={
            "invoice_id": str(invoice.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return invoice


# ---------------------------------------------------------------------------
# create_from_quote / create_from_sale
# ---------------------------------------------------------------------------


async def create_from_quote(
    session: AsyncSession,
    *,
    quote_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Invoice:
    """Create a draft invoice from an accepted quote.

    Copies line items, sets ``invoice.quote_id``, returns a fresh draft.
    The caller (``quotes.convert_to_invoice``) is responsible for setting
    ``quote.accepted_invoice_id`` and emitting
    ``ar.QuoteConvertedToInvoice``.
    """
    stmt = select(Quote).where(Quote.id == quote_id).options(selectinload(Quote.items))
    quote = (await session.execute(stmt)).scalar_one_or_none()
    if quote is None:
        raise InvoiceServiceError(f"quote {quote_id} not found")

    items: list[dict[str, Any]] = []
    for line in sorted(quote.items, key=lambda i: i.line_number):
        kind_value = line.kind.value if isinstance(line.kind, QuoteItemKind) else line.kind
        items.append(
            {
                "kind": kind_value,
                "product_id": line.product_id,
                "job_id": line.job_id,
                "description": line.description,
                "sku_or_job_number": line.sku_or_job_number,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
            }
        )

    return await create_draft(
        session,
        customer_id=quote.customer_id,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
        notes=quote.notes,
        items=items,
        quote_id=quote.id,
        actor_user_id=actor_user_id,
    )


async def create_from_sale(
    session: AsyncSession,
    *,
    sale_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Invoice:
    """STUB. See module docstring for rationale.

    Issuing an invoice on a sale that already posted Revenue (Phase 6.3
    sale-confirm) would double-count revenue. The clean fix needs an
    ``AR Pending`` clearing-account design — deferred to Phase 9.
    """
    raise NotImplementedError(
        "create_from_sale requires AR Pending clearing-account design; see Phase 9. "
        f"(requested sale_id={sale_id}, actor={actor_user_id})"
    )


# ---------------------------------------------------------------------------
# Account resolution at issue time
# ---------------------------------------------------------------------------


async def _resolve_setting_account(
    session: AsyncSession,
    *,
    keys: tuple[str, ...],
    why: str,
) -> uuid.UUID:
    """Try each ``keys`` in order; return the first set value or raise."""
    for key in keys:
        value = await SettingsService.get(key, session=session)
        if value is not None:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(str(value))
            return value
    pretty = ", ".join(repr(k) for k in keys)
    raise MissingArPostingAccountError(
        f"configure default AR posting accounts: none of {pretty} are set " f"(needed to {why})"
    )


async def _resolve_revenue_account(
    session: AsyncSession,
    *,
    customer: Customer,
) -> uuid.UUID:
    # No per-product/job revenue override column today; future hook.
    if customer.default_revenue_account_id is not None:
        return customer.default_revenue_account_id
    return await _resolve_setting_account(
        session,
        keys=(
            "ar.default_revenue_account_id",
            "sales_posting.default_ar_account_id",
        ),
        why="credit revenue for an invoice line",
    )


async def _resolve_ar_account(
    session: AsyncSession,
    *,
    customer: Customer,
) -> uuid.UUID:
    if customer.default_ar_account_id is not None:
        return customer.default_ar_account_id
    try:
        return await customers_service.resolve_default_ar_account(
            customer, channel=None, session=session
        )
    except customers_service.MissingDefaultAccountError:
        pass
    return await _resolve_setting_account(
        session,
        keys=(
            "ar.default_ar_account_id",
            "sales_posting.default_ar_account_id",
        ),
        why="debit AR for the invoice total",
    )


async def _resolve_tax_payable_account(session: AsyncSession) -> uuid.UUID:
    return await _resolve_setting_account(
        session,
        keys=(
            "ar.default_sales_tax_payable_account_id",
            "sales_posting.sales_tax_payable_account_id",
        ),
        why="credit sales tax payable on an invoice with tax",
    )


# ---------------------------------------------------------------------------
# State transitions: issue / void
# ---------------------------------------------------------------------------


async def issue(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Invoice:
    """Move ``draft -> issued`` and post the journal entry in the same TX.

    Re-snapshots ``billing_address`` (the customer may have edited it
    since draft creation), stamps ``issued_at = now()`` and ``due_at =
    issued_at + customer.payment_terms_days``, posts the AR/Revenue/Tax
    JE, stores ``posting_journal_entry_id`` on the invoice row, and
    emits ``ar.InvoiceIssued`` + ``ar.InvoicePosted``.
    """
    invoice = await _load(session, invoice_id)
    _ensure_transition(invoice.state, InvoiceState.ISSUED)

    customer = await _load_customer(session, invoice.customer_id)

    # Re-snapshot billing.
    invoice.billing_address_snapshot = (
        dict(customer.billing_address) if customer.billing_address is not None else None
    )

    issued_at = datetime.now(UTC)
    invoice.issued_at = issued_at
    if customer.payment_terms_days is not None:
        invoice.due_at = issued_at + timedelta(days=customer.payment_terms_days)

    invoice.state = InvoiceState.ISSUED

    # Resolve accounts BEFORE building the JE so a missing setting raises
    # before we touch anything.
    ar_account_id = await _resolve_ar_account(session, customer=customer)
    revenue_account_id = await _resolve_revenue_account(session, customer=customer)

    tax_amount = _q(invoice.tax_amount)
    sales_tax_payable_account_id: uuid.UUID | None = None
    if tax_amount > _ZERO:
        sales_tax_payable_account_id = await _resolve_tax_payable_account(session)

    subtotal = _q(invoice.subtotal)
    discount_amount = _q(invoice.discount_amount)
    total_amount = _q(invoice.total_amount)
    revenue_amount = _q(subtotal - discount_amount)

    # Build journal entry: debit AR (total), credit Revenue (subtotal - discount),
    # credit Sales Tax Payable (if tax > 0).
    lines_in: list[journal_service.JournalLineInput] = []
    line_no = 0

    def _next_line_no() -> int:
        nonlocal line_no
        line_no += 1
        return line_no

    if total_amount > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ar_account_id,
                debit=total_amount,
                credit=_ZERO,
                line_number=_next_line_no(),
                memo=f"AR for invoice {invoice.invoice_number}",
            )
        )
    if revenue_amount > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=revenue_account_id,
                debit=_ZERO,
                credit=revenue_amount,
                line_number=_next_line_no(),
                memo=f"Revenue for invoice {invoice.invoice_number}",
            )
        )
    if tax_amount > _ZERO and sales_tax_payable_account_id is not None:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=sales_tax_payable_account_id,
                debit=_ZERO,
                credit=tax_amount,
                line_number=_next_line_no(),
                memo=f"Sales tax payable for invoice {invoice.invoice_number}",
            )
        )

    if len(lines_in) < 2:
        raise InvoiceServiceError(
            f"invoice {invoice.invoice_number} has nothing to post (total is zero)"
        )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Invoice {invoice.invoice_number}: issuance",
            posted_at=issued_at,
            lines=lines_in,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    invoice.posting_journal_entry_id = entry.id
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_INVOICE_ISSUED,
        aggregate_id=invoice.id,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "customer_id": str(invoice.customer_id),
            "total_amount": str(total_amount),
            "issued_at": issued_at.isoformat(),
            "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
            "journal_entry_id": str(entry.id),
        },
        actor_user_id=actor_user_id,
    )
    await _emit(
        session,
        event_type=ar_events.TYPE_INVOICE_POSTED,
        aggregate_id=invoice.id,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "journal_entry_id": str(entry.id),
            "total_amount": str(total_amount),
        },
        actor_user_id=actor_user_id,
    )
    return invoice


async def void(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Invoice:
    """Void an invoice; reverse the posted JE (same TX).

    Only from ``issued / partially_paid / overdue`` — voiding a fully
    paid invoice is illegal (issue a refund / credit memo instead).
    If ``amount_paid > 0`` we raise ``InvoiceHasPaymentsError`` and
    point at Phase 7.4's unapply flow.
    """
    invoice = await _load(session, invoice_id)
    _ensure_transition(invoice.state, InvoiceState.VOID)

    if _q(invoice.amount_paid) > _ZERO:
        raise InvoiceHasPaymentsError(
            f"invoice {invoice.invoice_number} has applied payments "
            f"(amount_paid={invoice.amount_paid}); unapply via Phase 7.4 before voiding"
        )

    reversing_je_id: uuid.UUID | None = None
    original_je_id = invoice.posting_journal_entry_id
    if original_je_id is not None:
        reversal = await journal_service.reverse(
            original_je_id,
            session=session,
            actor_user_id=actor_user_id,
            description=f"Reversal of invoice {invoice.invoice_number}",
        )
        reversing_je_id = reversal.id

    invoice.state = InvoiceState.VOID
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_INVOICE_VOIDED,
        aggregate_id=invoice.id,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "customer_id": str(invoice.customer_id),
        },
        actor_user_id=actor_user_id,
    )
    if reversing_je_id is not None and original_je_id is not None:
        await _emit(
            session,
            event_type=ar_events.TYPE_INVOICE_REVERSED,
            aggregate_id=invoice.id,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "reversing_journal_entry_id": str(reversing_je_id),
                "original_journal_entry_id": str(original_je_id),
            },
            actor_user_id=actor_user_id,
        )
    return invoice


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> Invoice:
    return await _load(session, invoice_id, with_items=with_items)


@dataclass
class InvoicePage:
    items: list[Invoice]
    next_cursor: str | None


async def list_invoices(
    session: AsyncSession,
    *,
    state: str | None = None,
    customer_id: uuid.UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> InvoicePage:
    stmt = select(Invoice).options(selectinload(Invoice.items))
    if state is not None:
        try:
            stmt = stmt.where(Invoice.state == InvoiceState(state))
        except ValueError as exc:
            raise InvoiceServiceError(f"invalid state filter: {state!r}") from exc
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if due_before is not None:
        stmt = stmt.where(Invoice.due_at < due_before)
    if due_after is not None:
        stmt = stmt.where(Invoice.due_at > due_after)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Invoice.invoice_number.ilike(like))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Invoice.created_at < anchor_ts,
                and_(Invoice.created_at == anchor_ts, Invoice.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Invoice.created_at), desc(Invoice.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return InvoicePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "CustomerNotFoundForInvoiceError",
    "InvalidCursorError",
    "InvalidInvoiceItemError",
    "InvalidInvoiceStateError",
    "InvoiceHasPaymentsError",
    "InvoiceNotFoundError",
    "InvoicePage",
    "InvoiceServiceError",
    "MissingArPostingAccountError",
    "create_draft",
    "create_from_quote",
    "create_from_sale",
    "get",
    "issue",
    "list_invoices",
    "update_draft",
    "void",
]
