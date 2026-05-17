"""Recurring bills service (Phase 8.5, #132).

AP-side mirror of Phase 7.5's ``recurring_invoices`` service. Operators
configure a ``recurring_bill_template`` once; a worker materializes
draft bills on the configured cadence. The worker is gated by
``next_issue_at`` advance so re-running on the same ``now`` is a no-op
(idempotent).

Cadence math uses :mod:`dateutil.relativedelta` for monthly/yearly
arithmetic so adding 1 month to Jan 31 yields Feb 28/29 (rather than
rolling over to March 3).

If ``auto_issue=True`` on a template, the materialize step calls
``bills.issue(...)`` after creating the draft so the journal entry
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

from app.events.types import ap as ap_events
from app.models.bill import Bill
from app.models.recurring_bill import (
    RecurringBillCadenceKind,
    RecurringBillItemKind,
    RecurringBillTemplate,
    RecurringBillTemplateItem,
    RecurringBillTemplateState,
)
from app.models.vendor import Vendor
from app.schemas.events import EventCreate
from app.services import bills as bills_service
from app.services import event_store

log = logging.getLogger(__name__)

_QUANTUM = Decimal("0.000001")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RecurringBillServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class RecurringBillTemplateNotFoundError(RecurringBillServiceError):
    """Mapped to 404."""


class VendorNotFoundForTemplateError(RecurringBillServiceError):
    pass


class InvalidBillTemplateItemError(RecurringBillServiceError):
    pass


class InvalidBillTemplateStateError(RecurringBillServiceError):
    pass


class InvalidCursorError(RecurringBillServiceError):
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


def _cadence_delta(kind: RecurringBillCadenceKind | str, interval: int):
    kind_value = kind.value if isinstance(kind, RecurringBillCadenceKind) else kind
    if interval < 1:
        raise RecurringBillServiceError(f"cadence_interval must be >= 1, got {interval}")
    if kind_value == RecurringBillCadenceKind.DAILY.value:
        return timedelta(days=interval)
    if kind_value == RecurringBillCadenceKind.WEEKLY.value:
        return timedelta(weeks=interval)
    if kind_value == RecurringBillCadenceKind.MONTHLY.value:
        return relativedelta(months=interval)
    if kind_value == RecurringBillCadenceKind.QUARTERLY.value:
        return relativedelta(months=3 * interval)
    if kind_value == RecurringBillCadenceKind.YEARLY.value:
        return relativedelta(years=interval)
    raise RecurringBillServiceError(f"unknown cadence_kind: {kind_value!r}")


def compute_next_issue_at(
    template: RecurringBillTemplate | None = None,
    *,
    from_dt: datetime,
    cadence_kind: RecurringBillCadenceKind | str | None = None,
    cadence_interval: int | None = None,
) -> datetime:
    """Return ``from_dt + cadence``.

    Either pass a ``template`` (the worker path) or both ``cadence_kind``
    and ``cadence_interval`` (the pure / no-DB path used by tests).

    Uses :class:`dateutil.relativedelta` for month/year arithmetic so that
    Jan 31 + 1 month = Feb 28 (or Feb 29 on a leap year), not Mar 3.
    """
    if template is not None:
        kind = template.cadence_kind
        interval = template.cadence_interval
    else:
        if cadence_kind is None or cadence_interval is None:
            raise RecurringBillServiceError(
                "compute_next_issue_at requires template OR (cadence_kind + cadence_interval)"
            )
        kind = cadence_kind
        interval = cadence_interval
    return from_dt + _cadence_delta(kind, interval)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _coerce_item_kind(value: str | RecurringBillItemKind) -> RecurringBillItemKind:
    if isinstance(value, RecurringBillItemKind):
        return value
    try:
        return RecurringBillItemKind(value)
    except ValueError as exc:
        raise InvalidBillTemplateItemError(f"invalid item kind: {value!r}") from exc


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _coerce_item_kind(item.get("kind"))
    expense_category_id = item.get("expense_category_id")
    if isinstance(expense_category_id, str):
        try:
            expense_category_id = uuid.UUID(expense_category_id)
        except ValueError as exc:
            raise InvalidBillTemplateItemError(
                f"invalid expense_category_id: {expense_category_id!r}"
            ) from exc
    description = (item.get("description") or "").strip()
    if not description:
        raise InvalidBillTemplateItemError("item description is required")
    if kind == RecurringBillItemKind.EXPENSE_CATEGORY:
        if expense_category_id is None:
            raise InvalidBillTemplateItemError("kind=expense_category requires expense_category_id")
    else:  # MANUAL
        if expense_category_id is not None:
            raise InvalidBillTemplateItemError("kind=manual requires expense_category_id be null")
    try:
        quantity = _q(item.get("quantity", "1"))
        unit_price = _q(item.get("unit_price", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidBillTemplateItemError(f"invalid numeric value on item: {exc}") from exc
    if quantity <= 0:
        raise InvalidBillTemplateItemError("quantity must be positive")
    if unit_price < 0:
        raise InvalidBillTemplateItemError("unit_price must be non-negative")
    return {
        "kind": kind,
        "expense_category_id": expense_category_id,
        "description": description,
        "vendor_sku": item.get("vendor_sku"),
        "quantity": quantity,
        "unit_price": unit_price,
    }


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


async def _load(
    session: AsyncSession, template_id: uuid.UUID, *, with_items: bool = True
) -> RecurringBillTemplate:
    stmt = select(RecurringBillTemplate).where(RecurringBillTemplate.id == template_id)
    if with_items:
        stmt = stmt.options(selectinload(RecurringBillTemplate.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise RecurringBillTemplateNotFoundError(str(template_id))
    if with_items:
        await session.refresh(row, ["items"])
    return row


async def _load_vendor(session: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    stmt = select(Vendor).where(Vendor.id == vendor_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise VendorNotFoundForTemplateError(str(vendor_id))
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
            aggregate_type=ap_events.AGGREGATE_TYPE_RECURRING_BILL_TEMPLATE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _items_payload(items: list[RecurringBillTemplateItem]) -> list[dict[str, Any]]:
    return [
        {
            "line_number": i.line_number,
            "kind": (i.kind.value if isinstance(i.kind, RecurringBillItemKind) else i.kind),
            "expense_category_id": (str(i.expense_category_id) if i.expense_category_id else None),
            "description": i.description,
            "vendor_sku": i.vendor_sku,
            "quantity": str(i.quantity),
            "unit_price": str(i.unit_price),
        }
        for i in sorted(items, key=lambda x: x.line_number)
    ]


def _created_payload(template: RecurringBillTemplate) -> dict[str, Any]:
    return {
        "template_id": str(template.id),
        "name": template.name,
        "vendor_id": str(template.vendor_id),
        "cadence_kind": (
            template.cadence_kind.value
            if isinstance(template.cadence_kind, RecurringBillCadenceKind)
            else template.cadence_kind
        ),
        "cadence_interval": template.cadence_interval,
        "start_at": template.start_at.isoformat(),
        "end_at": template.end_at.isoformat() if template.end_at else None,
        "next_issue_at": template.next_issue_at.isoformat(),
        "auto_issue": template.auto_issue,
        "state": (
            template.state.value
            if isinstance(template.state, RecurringBillTemplateState)
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
    if isinstance(value, RecurringBillCadenceKind | RecurringBillTemplateState):
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
    vendor_id: uuid.UUID,
    name: str,
    cadence_kind: str | RecurringBillCadenceKind,
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
) -> RecurringBillTemplate:
    await _load_vendor(session, vendor_id)
    normalized_items = [_validate_item(raw) for raw in (items or [])]
    kind_enum = (
        cadence_kind
        if isinstance(cadence_kind, RecurringBillCadenceKind)
        else RecurringBillCadenceKind(cadence_kind)
    )

    template = RecurringBillTemplate(
        vendor_id=vendor_id,
        name=name,
        cadence_kind=kind_enum,
        cadence_interval=cadence_interval,
        start_at=start_at,
        end_at=end_at,
        next_issue_at=start_at,
        auto_issue=auto_issue,
        state=RecurringBillTemplateState.ACTIVE,
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
            RecurringBillTemplateItem(
                template_id=template.id,
                line_number=idx,
                kind=item["kind"],
                expense_category_id=item["expense_category_id"],
                description=item["description"],
                vendor_sku=item["vendor_sku"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidBillTemplateItemError(
            f"recurring bill template item integrity violation: {exc.orig}"
        ) from exc

    template = await _load(session, template.id)
    await _emit(
        session,
        event_type=ap_events.TYPE_RECURRING_BILL_TEMPLATE_CREATED,
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
) -> RecurringBillTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringBillTemplateState.CANCELLED:
        raise InvalidBillTemplateStateError(
            f"recurring bill template {template_id} is cancelled; cannot edit"
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
            and not isinstance(new_value, RecurringBillCadenceKind)
        ):
            new_value = RecurringBillCadenceKind(new_value)
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
                RecurringBillTemplateItem(
                    template_id=template.id,
                    line_number=idx,
                    kind=item["kind"],
                    expense_category_id=item["expense_category_id"],
                    description=item["description"],
                    vendor_sku=item["vendor_sku"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                )
            )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise InvalidBillTemplateItemError(
                f"recurring bill template item integrity violation: {exc.orig}"
            ) from exc

    if not before and not items_changed:
        return template

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
        event_type=ap_events.TYPE_RECURRING_BILL_TEMPLATE_UPDATED,
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
) -> RecurringBillTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringBillTemplateState.CANCELLED:
        raise InvalidBillTemplateStateError("cannot pause a cancelled template")
    if template.state == RecurringBillTemplateState.PAUSED:
        return template
    template.state = RecurringBillTemplateState.PAUSED
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_RECURRING_BILL_TEMPLATE_PAUSED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "vendor_id": str(template.vendor_id),
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
) -> RecurringBillTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringBillTemplateState.CANCELLED:
        raise InvalidBillTemplateStateError("cannot resume a cancelled template")
    if template.state == RecurringBillTemplateState.ACTIVE:
        return template
    template.state = RecurringBillTemplateState.ACTIVE
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_RECURRING_BILL_TEMPLATE_RESUMED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "vendor_id": str(template.vendor_id),
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
) -> RecurringBillTemplate:
    template = await _load(session, template_id)
    if template.state == RecurringBillTemplateState.CANCELLED:
        return template
    template.state = RecurringBillTemplateState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_RECURRING_BILL_TEMPLATE_CANCELLED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "vendor_id": str(template.vendor_id),
            "cadence_kind": _serialize(template.cadence_kind),
        },
        actor_user_id=actor_user_id,
    )
    return template


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def _build_bill_items_payload(
    items: list[RecurringBillTemplateItem],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in sorted(items, key=lambda i: i.line_number):
        kind_value = line.kind.value if isinstance(line.kind, RecurringBillItemKind) else line.kind
        out.append(
            {
                "kind": kind_value,
                "expense_category_id": line.expense_category_id,
                "description": line.description,
                "vendor_sku": line.vendor_sku,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
            }
        )
    return out


async def _materialize_one(
    session: AsyncSession,
    *,
    template: RecurringBillTemplate,
    now: datetime,
    actor_user_id: uuid.UUID | None,
    ignore_cadence: bool = False,
) -> Bill:
    """Materialize one template into a draft bill (and optionally issue).

    Updates ``last_issued_at`` and ``next_issue_at`` on the template,
    emits ``ap.RecurringBillMaterialized``. Caller commits.
    """
    items_in = _build_bill_items_payload(template.items)
    bill = await bills_service.create_draft(
        session,
        vendor_id=template.vendor_id,
        discount_amount=template.discount_amount,
        tax_amount=template.tax_amount,
        notes=template.notes,
        items=items_in,
        currency=template.currency,
        actor_user_id=actor_user_id or template.created_by_user_id,
    )

    auto_issued = False
    if template.auto_issue:
        bill = await bills_service.issue(
            session,
            bill_id=bill.id,
            actor_user_id=actor_user_id or template.created_by_user_id,
        )
        auto_issued = True

    template.last_issued_at = now
    nia = template.next_issue_at
    if nia.tzinfo is None:
        nia = nia.replace(tzinfo=UTC)
    if ignore_cadence:
        if nia <= now:
            nia = compute_next_issue_at(template, from_dt=nia)
    else:
        nia = compute_next_issue_at(template, from_dt=nia)
        while nia <= now:
            nia = compute_next_issue_at(template, from_dt=nia)
    template.next_issue_at = nia

    end_at = template.end_at
    if end_at is not None:
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=UTC)
        if nia > end_at:
            template.state = RecurringBillTemplateState.CANCELLED

    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_RECURRING_BILL_MATERIALIZED,
        aggregate_id=template.id,
        payload={
            "template_id": str(template.id),
            "name": template.name,
            "vendor_id": str(template.vendor_id),
            "cadence_kind": _serialize(template.cadence_kind),
            "bill_id": str(bill.id),
            "bill_number": bill.bill_number,
            "materialized_at": now.isoformat(),
            "auto_issued": auto_issued,
            "next_issue_at": template.next_issue_at.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    return bill


async def materialize_due(
    *,
    session: AsyncSession,
    now: datetime,
    dry_run: bool = False,
    actor_user_id: uuid.UUID | None = None,
) -> list[Bill]:
    """Materialize all active templates with ``next_issue_at <= now``."""
    stmt = (
        select(RecurringBillTemplate)
        .where(RecurringBillTemplate.state == RecurringBillTemplateState.ACTIVE)
        .where(RecurringBillTemplate.next_issue_at <= now)
        .where(
            or_(
                RecurringBillTemplate.end_at.is_(None),
                RecurringBillTemplate.end_at >= now,
            )
        )
        .options(selectinload(RecurringBillTemplate.items))
        .order_by(RecurringBillTemplate.next_issue_at.asc())
    )
    rows = list((await session.execute(stmt)).scalars().all())

    created: list[Bill] = []
    for template in rows:
        if dry_run:
            continue
        try:
            bill = await _materialize_one(
                session, template=template, now=now, actor_user_id=actor_user_id
            )
            created.append(bill)
        except Exception:
            log.exception(
                "recurring_bills.materialize_one failed",
                extra={"template_id": str(template.id)},
            )
            continue
    return created


async def materialize_now(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Bill:
    """Operator-triggered: ignore cadence + state filter."""
    template = await _load(session, template_id)
    if template.state == RecurringBillTemplateState.CANCELLED:
        raise InvalidBillTemplateStateError("cannot materialize a cancelled template")
    now = datetime.now(UTC)
    bill = await _materialize_one(
        session,
        template=template,
        now=now,
        actor_user_id=actor_user_id,
        ignore_cadence=True,
    )
    return bill


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(
    session: AsyncSession,
    template_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> RecurringBillTemplate:
    return await _load(session, template_id, with_items=with_items)


@dataclass
class RecurringBillTemplatePage:
    items: list[RecurringBillTemplate]
    next_cursor: str | None


async def list_templates(
    session: AsyncSession,
    *,
    state: str | None = None,
    vendor_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> RecurringBillTemplatePage:
    stmt = select(RecurringBillTemplate).options(selectinload(RecurringBillTemplate.items))
    if state is not None:
        try:
            stmt = stmt.where(RecurringBillTemplate.state == RecurringBillTemplateState(state))
        except ValueError as exc:
            raise RecurringBillServiceError(f"invalid state filter: {state!r}") from exc
    if vendor_id is not None:
        stmt = stmt.where(RecurringBillTemplate.vendor_id == vendor_id)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                RecurringBillTemplate.created_at < anchor_ts,
                and_(
                    RecurringBillTemplate.created_at == anchor_ts,
                    RecurringBillTemplate.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(
        desc(RecurringBillTemplate.created_at), desc(RecurringBillTemplate.id)
    ).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return RecurringBillTemplatePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidBillTemplateItemError",
    "InvalidBillTemplateStateError",
    "InvalidCursorError",
    "RecurringBillServiceError",
    "RecurringBillTemplateNotFoundError",
    "RecurringBillTemplatePage",
    "VendorNotFoundForTemplateError",
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
