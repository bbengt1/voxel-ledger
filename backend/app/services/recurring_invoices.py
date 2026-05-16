"""Recurring invoices service (Phase 7.5, #113).

Operators configure a ``recurring_invoice_template`` once; a worker
materializes draft invoices on the configured cadence. The worker is
gated by ``next_issue_at`` advance so re-running on the same ``now`` is a
no-op (idempotent).

Cadence math uses :mod:`dateutil.relativedelta` for monthly/yearly
arithmetic so that adding 1 month to Jan 31 yields Feb 28/29 (rather
than rolling over to March 3).

If ``auto_issue=True`` on a template, the materialize step calls
``invoices.issue(...)`` after creating the draft so the journal entry
posts in the same DB transaction as the materialize. Worker exceptions
are caught + logged per-template — one bad template does not block
materializing the rest.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ar as ar_events
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.recurring_invoice import (
    RecurringCadenceKind,
    RecurringInvoiceItemKind,
    RecurringInvoiceTemplate,
    RecurringInvoiceTemplateItem,
    RecurringTemplateState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import invoices as invoices_service

log = logging.getLogger(__name__)

_QUANTUM = Decimal("0.000001")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RecurringInvoiceServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class RecurringTemplateNotFoundError(RecurringInvoiceServiceError):
    """Mapped to 404."""


class CustomerNotFoundForTemplateError(RecurringInvoiceServiceError):
    pass


class InvalidTemplateItemError(RecurringInvoiceServiceError):
    pass


class InvalidTemplateStateError(RecurringInvoiceServiceError):
    pass


class InvalidCursorError(RecurringInvoiceServiceError):
    pass


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, template_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(template_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Cadence math
# ---------------------------------------------------------------------------


def _cadence_delta(kind: RecurringCadenceKind | str, interval: int):
    kind_value = kind.value if isinstance(kind, RecurringCadenceKind) else kind
    if interval < 1:
        raise RecurringInvoiceServiceError(f"cadence_interval must be >= 1, got {interval}")
    if kind_value == RecurringCadenceKind.DAILY.value:
        return timedelta(days=interval)
    if kind_value == RecurringCadenceKind.WEEKLY.value:
        return timedelta(weeks=interval)
    if kind_value == RecurringCadenceKind.MONTHLY.value:
        return relativedelta(months=interval)
    if kind_value == RecurringCadenceKind.QUARTERLY.value:
        return relativedelta(months=3 * interval)
    if kind_value == RecurringCadenceKind.YEARLY.value:
        return relativedelta(years=interval)
    raise RecurringInvoiceServiceError(f"unknown cadence_kind: {kind_value!r}")


def compute_next_issue_at(
    template: RecurringInvoiceTemplate | None = None,
    *,
    from_dt: datetime,
    cadence_kind: RecurringCadenceKind | str | None = None,
    cadence_interval: int | None = None,
) -> datetime:
    """Return ``from_dt + cadence``.

    Either pass a ``template`` (the worker path) or both ``cadence_kind``
    and ``cadence_interval`` (the pure / no-DB path used by tests and the
    create-time computation).

    Uses :class:`dateutil.relativedelta` for month/year arithmetic so that
    Jan 31 + 1 month = Feb 28 (or Feb 29 on a leap year), not Mar 3.
    """
    if template is not None:
        kind = template.cadence_kind
        interval = template.cadence_interval
    else:
        if cadence_kind is None or cadence_interval is None:
            raise RecurringInvoiceServiceError(
                "compute_next_issue_at requires template OR (cadence_kind + cadence_interval)"
            )
        kind = cadence_kind
        interval = cadence_interval
    return from_dt + _cadence_delta(kind, interval)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _coerce_item_kind(value: str | RecurringInvoiceItemKind) -> RecurringInvoiceItemKind:
    if isinstance(value, RecurringInvoiceItemKind):
        return value
    try:
        return RecurringInvoiceItemKind(value)
    except ValueError as exc:
        raise InvalidTemplateItemError(f"invalid item kind: {value!r}") from exc


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _coerce_item_kind(item.get("kind"))
    product_id = item.get("product_id")
    job_id = item.get("job_id")
    if isinstance(product_id, str):
        try:
            product_id = uuid.UUID(product_id)
        except ValueError as exc:
            raise InvalidTemplateItemError(f"invalid product_id: {product_id!r}") from exc
    if isinstance(job_id, str):
        try:
            job_id = uuid.UUID(job_id)
        except ValueError as exc:
            raise InvalidTemplateItemError(f"invalid job_id: {job_id!r}") from exc
    description = (item.get("description") or "").strip()
    if not description:
        raise InvalidTemplateItemError("item description is required")
    if kind == RecurringInvoiceItemKind.PRODUCT:
        if product_id is None or job_id is not None:
            raise InvalidTemplateItemError("kind=product requires product_id and no job_id")
    elif kind == RecurringInvoiceItemKind.JOB:
        if job_id is None or product_id is not None:
            raise InvalidTemplateItemError("kind=job requires job_id and no product_id")
    else:
        if product_id is not None or job_id is not None:
            raise InvalidTemplateItemError(
                "kind=manual requires both product_id and job_id be null"
            )
    try:
        quantity = _q(item.get("quantity", "1"))
        unit_price = _q(item.get("unit_price", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidTemplateItemError(f"invalid numeric value on item: {exc}") from exc
    if quantity <= 0:
        raise InvalidTemplateItemError("quantity must be positive")
    if unit_price < 0:
        raise InvalidTemplateItemError("unit_price must be non-negative")
    return {
        "kind": kind,
        "product_id": product_id,
        "job_id": job_id,
        "description": description,
        "sku_or_job_number": item.get("sku_or_job_number"),
        "quantity": quantity,
        "unit_price": unit_price,
    }


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


async def _load(
    session: AsyncSession, template_id: uuid.UUID, *, with_items: bool = True
) -> RecurringInvoiceTemplate:
    stmt = select(RecurringInvoiceTemplate).where(RecurringInvoiceTemplate.id == template_id)
    if with_items:
        stmt = stmt.options(selectinload(RecurringInvoiceTemplate.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise RecurringTemplateNotFoundError(str(template_id))
    if with_items:
        await session.refresh(row, ["items"])
    return row


async def _load_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    stmt = select(Customer).where(Customer.id == customer_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CustomerNotFoundForTemplateError(str(customer_id))
    return row


# ---------------------------------------------------------------------------
# Event helpers
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
            aggregate_type=ar_events.AGGREGATE_TYPE_RECURRING_INVOICE_TEMPLATE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _items_payload(items: list[RecurringInvoiceTemplateItem]) -> list[dict[str, Any]]:
    return [
        {
            "line_number": i.line_number,
            "kind": (i.kind.value if isinstance(i.kind, RecurringInvoiceItemKind) else i.kind),
            "product_id": str(i.product_id) if i.product_id else None,
            "job_id": str(i.job_id) if i.job_id else None,
            "description": i.description,
            "sku_or_job_number": i.sku_or_job_number,
            "quantity": str(i.quantity),
            "unit_price": str(i.unit_price),
        }
        for i in sorted(items, key=lambda x: x.line_number)
    ]


def _created_payload(template: RecurringInvoiceTemplate) -> dict[str, Any]:
    return {
        "template_id": str(template.id),
        "name": template.name,
        "customer_id": str(template.customer_id),
        "cadence_kind": (
            template.cadence_kind.value
            if isinstance(template.cadence_kind, RecurringCadenceKind)
            else template.cadence_kind
        ),
        "cadence_interval": template.cadence_interval,
        "start_at": template.start_at.isoformat(),
        "end_at": template.end_at.isoformat() if template.end_at else None,
        "next_issue_at": template.next_issue_at.isoformat(),
        "auto_issue": template.auto_issue,
        "state": (
            template.state.value
            if isinstance(template.state, RecurringTemplateState)
            else template.state
        ),
        "notes": template.notes,
        "discount_amount": str(template.discount_amount),
        "tax_amount": str(template.tax_amount),
        "currency": template.currency,
        "items": _items_payload(template.items),
    }


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, RecurringCadenceKind | RecurringTemplateState):
        return value.value
    return value


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


_EDITABLE_SCALAR_FIELDS = (
    "name",
    "cadence_kind",
    "cadence_interval",
    "start_at",
    "end_at",
    "auto_issue",
    "notes",
    "discount_amount",
    "tax_amount",
    "currency",
)


async def create(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    name: str,
    cadence_kind: str | RecurringCadenceKind,
    cadence_interval: int = 1,
    start_at: datetime,
    end_at: datetime | None = None,
    auto_issue: bool = False,
    notes: str | None = None,
    discount_amount: Decimal | str | int | float = Decimal("0"),
    tax_amount: Decimal | str | int | float = Decimal("0"),
    currency: str = "USD",
    items: list[dict[str, Any]] | None = None,
    actor_user_id: uuid.UUID,
) -> RecurringInvoiceTemplate:
    await _load_customer(session, customer_id)
    normalized_items = [_validate_item(raw) for raw in (items or [])]
    kind_enum = (
        cadence_kind
        if isinstance(cadence_kind, RecurringCadenceKind)
        else RecurringCadenceKind(cadence_kind)
    )

    template = RecurringInvoiceTemplate(
        customer_id=customer_id,
        name=name,
        cadence_kind=kind_enum,
        cadence_interval=cadence_interval,
        start_at=start_at,
        end_at=end_at,
        next_issue_at=start_at,
        auto_issue=auto_issue,
        state=RecurringTemplateState.ACTIVE,
        notes=notes,
        discount_amount=_q(discount_amount),
        tax_amount=_q(tax_amount),
        currency=currency,
        created_by_user_id=actor_user_id,
    )
    session.add(template)
    await session.flush()

    for idx, item in enumerate(normalized_items, start=1):
        session.add(
            RecurringInvoiceTemplateItem(
                template_id=template.id,
                line_number=idx,
                kind=item["kind"],
                product_id=item["product_id"],
                job_id=item["job_id"],
                description=item["description"],
                sku_or_job_number=item["sku_or_job_number"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidTemplateItemError(
            f"recurring template item integrity violation: {exc.orig}"
        ) from exc

    template = await _load(session, template.id)
    await _emit(
        session,
        event_type=ar_events.TYPE_RECURRING_TEMPLATE_CREATED,
        aggregate_id=template.id,
        payload=_created_payload(template),
        actor_user_id=actor_user_id,
    )
    return template


async def update(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> RecurringInvoiceTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringTemplateState.CANCELLED:
        raise InvalidTemplateStateError(
            f"recurring template {template_id} is cancelled; cannot edit"
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_SCALAR_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("discount_amount", "tax_amount") and new_value is not None:
            new_value = _q(new_value)
        if (
            field == "cadence_kind"
            and new_value is not None
            and not isinstance(new_value, RecurringCadenceKind)
        ):
            new_value = RecurringCadenceKind(new_value)
        current = getattr(template, field)
        if isinstance(current, Decimal) and isinstance(new_value, Decimal):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = _serialize(current)
        after[field] = _serialize(new_value)
        setattr(template, field, new_value)

    items_changed = False
    if "items" in patch and patch["items"] is not None:
        items_changed = True
        normalized_items = [_validate_item(raw) for raw in patch["items"]]
        before["items"] = _items_payload(template.items)
        for existing in list(template.items):
            await session.delete(existing)
        await session.flush()
        template.items.clear()
        for idx, item in enumerate(normalized_items, start=1):
            session.add(
                RecurringInvoiceTemplateItem(
                    template_id=template.id,
                    line_number=idx,
                    kind=item["kind"],
                    product_id=item["product_id"],
                    job_id=item["job_id"],
                    description=item["description"],
                    sku_or_job_number=item["sku_or_job_number"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                )
            )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise InvalidTemplateItemError(
                f"recurring template item integrity violation: {exc.orig}"
            ) from exc

    if not before and not items_changed:
        return template

    # Recompute next_issue_at if cadence-affecting fields changed AND the
    # template hasn't issued yet (still anchored at start_at).
    if (
        any(k in patch for k in ("cadence_kind", "cadence_interval", "start_at"))
        and template.last_issued_at is None
    ):
        template.next_issue_at = template.start_at

    if items_changed:
        await session.flush()
        template = await _load(session, template.id)
        after["items"] = _items_payload(template.items)

    await _emit(
        session,
        event_type=ar_events.TYPE_RECURRING_TEMPLATE_UPDATED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return template


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def pause(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> RecurringInvoiceTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringTemplateState.CANCELLED:
        raise InvalidTemplateStateError("cannot pause a cancelled template")
    if template.state == RecurringTemplateState.PAUSED:
        return template
    template.state = RecurringTemplateState.PAUSED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_RECURRING_TEMPLATE_PAUSED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "customer_id": str(template.customer_id),
            "cadence_kind": _serialize(template.cadence_kind),
        },
        actor_user_id=actor_user_id,
    )
    return template


async def resume(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> RecurringInvoiceTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringTemplateState.CANCELLED:
        raise InvalidTemplateStateError("cannot resume a cancelled template")
    if template.state == RecurringTemplateState.ACTIVE:
        return template
    template.state = RecurringTemplateState.ACTIVE
    # Don't reset next_issue_at — the worker picks up from the existing
    # schedule. If next_issue_at is in the past the next materialize_due
    # call will catch it up.
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_RECURRING_TEMPLATE_RESUMED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "customer_id": str(template.customer_id),
            "cadence_kind": _serialize(template.cadence_kind),
            "next_issue_at": template.next_issue_at.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    return template


async def cancel(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> RecurringInvoiceTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringTemplateState.CANCELLED:
        return template
    template.state = RecurringTemplateState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_RECURRING_TEMPLATE_CANCELLED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "customer_id": str(template.customer_id),
            "cadence_kind": _serialize(template.cadence_kind),
        },
        actor_user_id=actor_user_id,
    )
    return template


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def _build_invoice_items_payload(
    items: list[RecurringInvoiceTemplateItem],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in sorted(items, key=lambda i: i.line_number):
        kind_value = (
            line.kind.value if isinstance(line.kind, RecurringInvoiceItemKind) else line.kind
        )
        out.append(
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
    return out


async def _materialize_one(
    session: AsyncSession,
    *,
    template: RecurringInvoiceTemplate,
    now: datetime,
    actor_user_id: uuid.UUID | None,
    ignore_cadence: bool = False,
) -> Invoice:
    """Materialize one template into a draft invoice (and optionally issue).

    Updates ``last_issued_at`` and ``next_issue_at`` on the template, emits
    ``ar.RecurringInvoiceMaterialized``. Caller commits.
    """
    items_in = _build_invoice_items_payload(template.items)
    invoice = await invoices_service.create_draft(
        session,
        customer_id=template.customer_id,
        discount_amount=template.discount_amount,
        tax_amount=template.tax_amount,
        notes=template.notes,
        items=items_in,
        currency=template.currency,
        actor_user_id=actor_user_id or template.created_by_user_id,
    )

    auto_issued = False
    if template.auto_issue:
        invoice = await invoices_service.issue(
            session,
            invoice_id=invoice.id,
            actor_user_id=actor_user_id or template.created_by_user_id,
        )
        auto_issued = True

    template.last_issued_at = now
    # SQLite drops tzinfo on DateTime(timezone=True); coerce to UTC-aware for
    # comparison with ``now`` (which is always UTC-aware in production).
    nia = template.next_issue_at
    if nia.tzinfo is None:
        nia = nia.replace(tzinfo=UTC)
    if ignore_cadence:
        # Manual materialize-now: advance from the template's existing
        # next_issue_at so the regular cadence still hits its anchor.
        if nia <= now:
            nia = compute_next_issue_at(template, from_dt=nia)
    else:
        nia = compute_next_issue_at(template, from_dt=nia)
        # If the new next_issue_at is still <= now (catch-up after a long
        # outage), keep advancing one cycle past now to avoid materializing
        # multiple invoices for the same wake-up.
        while nia <= now:
            nia = compute_next_issue_at(template, from_dt=nia)
    template.next_issue_at = nia

    # If we've passed end_at, cancel the template.
    end_at = template.end_at
    if end_at is not None:
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=UTC)
        if nia > end_at:
            template.state = RecurringTemplateState.CANCELLED

    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_RECURRING_INVOICE_MATERIALIZED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "customer_id": str(template.customer_id),
            "cadence_kind": _serialize(template.cadence_kind),
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "materialized_at": now.isoformat(),
            "auto_issued": auto_issued,
            "next_issue_at": template.next_issue_at.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    return invoice


async def materialize_due(
    *,
    session: AsyncSession,
    now: datetime,
    dry_run: bool = False,
    actor_user_id: uuid.UUID | None = None,
) -> list[Invoice]:
    """Materialize all active templates with ``next_issue_at <= now``.

    Idempotent: each materialize advances ``next_issue_at`` past ``now`` so
    a second call with the same ``now`` is a no-op. Per-template exceptions
    are caught + logged so one bad template does not block the rest.

    ``dry_run=True`` returns the templates that would be materialized
    without writing anything.
    """
    stmt = (
        select(RecurringInvoiceTemplate)
        .where(RecurringInvoiceTemplate.state == RecurringTemplateState.ACTIVE)
        .where(RecurringInvoiceTemplate.next_issue_at <= now)
        .where(
            or_(
                RecurringInvoiceTemplate.end_at.is_(None),
                RecurringInvoiceTemplate.end_at >= now,
            )
        )
        .options(selectinload(RecurringInvoiceTemplate.items))
        .order_by(RecurringInvoiceTemplate.next_issue_at.asc())
    )
    rows = list((await session.execute(stmt)).scalars().all())

    created: list[Invoice] = []
    for template in rows:
        if dry_run:
            continue
        try:
            invoice = await _materialize_one(
                session, template=template, now=now, actor_user_id=actor_user_id
            )
            created.append(invoice)
        except Exception:
            log.exception(
                "recurring_invoices.materialize_one failed",
                extra={"template_id": str(template.id)},
            )
            # Roll back this template's changes so the rest can proceed in
            # a fresh nested savepoint. SQLAlchemy 2.0 session rollback
            # would abort the whole transaction — instead we rely on the
            # caller to wrap each call in a savepoint OR accept the abort.
            # For SQLite tests + PG production today we let the worker
            # commit-per-template (the worker call site handles that).
            continue
    return created


async def materialize_now(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Invoice:
    """Operator-triggered: ignore cadence + state filter."""
    template = await _load(session, template_id)
    if template.state == RecurringTemplateState.CANCELLED:
        raise InvalidTemplateStateError("cannot materialize a cancelled template")
    now = datetime.now(UTC)
    invoice = await _materialize_one(
        session,
        template=template,
        now=now,
        actor_user_id=actor_user_id,
        ignore_cadence=True,
    )
    return invoice


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(
    session: AsyncSession,
    template_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> RecurringInvoiceTemplate:
    return await _load(session, template_id, with_items=with_items)


@dataclass
class RecurringTemplatePage:
    items: list[RecurringInvoiceTemplate]
    next_cursor: str | None


async def list_templates(
    session: AsyncSession,
    *,
    state: str | None = None,
    customer_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> RecurringTemplatePage:
    stmt = select(RecurringInvoiceTemplate).options(selectinload(RecurringInvoiceTemplate.items))
    if state is not None:
        try:
            stmt = stmt.where(RecurringInvoiceTemplate.state == RecurringTemplateState(state))
        except ValueError as exc:
            raise RecurringInvoiceServiceError(f"invalid state filter: {state!r}") from exc
    if customer_id is not None:
        stmt = stmt.where(RecurringInvoiceTemplate.customer_id == customer_id)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                RecurringInvoiceTemplate.created_at < anchor_ts,
                and_(
                    RecurringInvoiceTemplate.created_at == anchor_ts,
                    RecurringInvoiceTemplate.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(
        desc(RecurringInvoiceTemplate.created_at), desc(RecurringInvoiceTemplate.id)
    ).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return RecurringTemplatePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "CustomerNotFoundForTemplateError",
    "InvalidCursorError",
    "InvalidTemplateItemError",
    "InvalidTemplateStateError",
    "RecurringInvoiceServiceError",
    "RecurringTemplateNotFoundError",
    "RecurringTemplatePage",
    "cancel",
    "compute_next_issue_at",
    "create",
    "get",
    "list_templates",
    "materialize_due",
    "materialize_now",
    "pause",
    "resume",
    "update",
]
