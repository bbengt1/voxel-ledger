"""Batch operations service (Phase 11.3, #195).

A single generic preview / commit flow with per-entity adapters. Each
adapter handles one entity type and declares the actions it supports
along with any blockers that prevent a row from being acted on.

Surface
-------
:func:`preview` -> ``BatchPreview{matched_count, sample, blockers}``
  Pure-read; no mutations. Returns up to 10 sample rows plus the full
  blocker list keyed by row id so the UI can show "won't archive X
  because it has an open invoice".

:func:`commit`  -> ``BatchResult{applied, skipped, audit_id}``
  Single transaction. Applies the action to every actionable row;
  rows blocked by the adapter are skipped. Always writes one
  ``audit_log`` row via the audit service, with row ids only (no PII).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import batch_ops as batch_ops_events
from app.models.bill import Bill, BillState
from app.models.customer import Customer, CustomerState
from app.models.invoice import Invoice, InvoiceState
from app.models.product import Product
from app.models.vendor import Vendor, VendorState
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BatchOpsError(Exception):
    """Base. Routers default to 400."""


class UnknownEntityError(BatchOpsError):
    """Mapped to 400."""


class UnknownActionError(BatchOpsError):
    """Mapped to 400."""


class InvalidActionParamsError(BatchOpsError):
    """Mapped to 400."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Blocker:
    id: uuid.UUID
    reason: str


@dataclass
class BatchPreview:
    entity: str
    action: str
    matched_count: int
    sample: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)


@dataclass
class BatchResult:
    entity: str
    action: str
    applied: int
    skipped: int
    audit_id: uuid.UUID
    blockers: list[Blocker] = field(default_factory=list)


# Adapter protocol -----------------------------------------------------------

LoadFn = Callable[[AsyncSession, list[uuid.UUID]], Awaitable[list[Any]]]
SummariseFn = Callable[[Any], dict[str, Any]]
BlockerFn = Callable[[AsyncSession, Any, str], Awaitable[str | None]]
ApplyFn = Callable[[Any, str, dict[str, Any]], None]


@dataclass(frozen=True)
class Adapter:
    entity: str
    actions: frozenset[str]
    load: LoadFn
    summarise: SummariseFn
    blocker: BlockerFn
    apply: ApplyFn
    valid_params: Callable[[str, dict[str, Any]], None] = lambda action, params: None


# ---------------------------------------------------------------------------
# Customer adapter
# ---------------------------------------------------------------------------


async def _load_customers(session: AsyncSession, ids: list[uuid.UUID]) -> list[Customer]:
    if not ids:
        return []
    rows = (await session.execute(select(Customer).where(Customer.id.in_(ids)))).scalars().all()
    return list(rows)


def _summarise_customer(c: Customer) -> dict[str, Any]:
    return {"id": str(c.id), "display_name": c.display_name, "state": c.state.value}


async def _customer_blocker(session: AsyncSession, c: Customer, action: str) -> str | None:
    if action == "archive":
        if c.state == CustomerState.ARCHIVED:
            return "already archived"
        open_inv = (
            await session.execute(
                select(Invoice.id)
                .where(Invoice.customer_id == c.id)
                .where(Invoice.amount_outstanding > Decimal("0"))
                .limit(1)
            )
        ).first()
        if open_inv is not None:
            return "customer has open invoices"
        return None
    if action == "unarchive":
        if c.state != CustomerState.ARCHIVED:
            return "not archived"
        return None
    return f"unsupported action {action!r}"


def _apply_customer(c: Customer, action: str, params: dict[str, Any]) -> None:
    if action == "archive":
        c.state = CustomerState.ARCHIVED
    elif action == "unarchive":
        c.state = CustomerState.ACTIVE


CUSTOMER_ADAPTER = Adapter(
    entity="customer",
    actions=frozenset({"archive", "unarchive"}),
    load=_load_customers,
    summarise=_summarise_customer,
    blocker=_customer_blocker,
    apply=_apply_customer,
)


# ---------------------------------------------------------------------------
# Vendor adapter
# ---------------------------------------------------------------------------


async def _load_vendors(session: AsyncSession, ids: list[uuid.UUID]) -> list[Vendor]:
    if not ids:
        return []
    return list((await session.execute(select(Vendor).where(Vendor.id.in_(ids)))).scalars().all())


def _summarise_vendor(v: Vendor) -> dict[str, Any]:
    return {"id": str(v.id), "display_name": v.display_name, "state": v.state.value}


async def _vendor_blocker(session: AsyncSession, v: Vendor, action: str) -> str | None:
    if action == "archive":
        if v.state == VendorState.ARCHIVED:
            return "already archived"
        open_bill = (
            await session.execute(
                select(Bill.id)
                .where(Bill.vendor_id == v.id)
                .where(Bill.amount_outstanding > Decimal("0"))
                .limit(1)
            )
        ).first()
        if open_bill is not None:
            return "vendor has open bills"
        return None
    if action == "unarchive":
        if v.state != VendorState.ARCHIVED:
            return "not archived"
        return None
    return f"unsupported action {action!r}"


def _apply_vendor(v: Vendor, action: str, params: dict[str, Any]) -> None:
    if action == "archive":
        v.state = VendorState.ARCHIVED
    elif action == "unarchive":
        v.state = VendorState.ACTIVE


VENDOR_ADAPTER = Adapter(
    entity="vendor",
    actions=frozenset({"archive", "unarchive"}),
    load=_load_vendors,
    summarise=_summarise_vendor,
    blocker=_vendor_blocker,
    apply=_apply_vendor,
)


# ---------------------------------------------------------------------------
# Product adapter
# ---------------------------------------------------------------------------


async def _load_products(session: AsyncSession, ids: list[uuid.UUID]) -> list[Product]:
    if not ids:
        return []
    return list((await session.execute(select(Product).where(Product.id.in_(ids)))).scalars().all())


def _summarise_product(p: Product) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "sku": p.sku,
        "name": p.name,
        "category": p.category,
        "is_archived": p.is_archived,
    }


async def _product_blocker(session: AsyncSession, p: Product, action: str) -> str | None:
    _ = session  # unused for products
    if action == "archive":
        return "already archived" if p.is_archived else None
    if action == "unarchive":
        return None if p.is_archived else "not archived"
    if action == "set_category":
        return None
    return f"unsupported action {action!r}"


def _apply_product(p: Product, action: str, params: dict[str, Any]) -> None:
    if action == "archive":
        p.is_archived = True
    elif action == "unarchive":
        p.is_archived = False
    elif action == "set_category":
        p.category = params.get("category") or None


def _validate_product_params(action: str, params: dict[str, Any]) -> None:
    if action == "set_category":
        if "category" not in params:
            raise InvalidActionParamsError("'set_category' requires a 'category' param")
        if params["category"] is not None and not isinstance(params["category"], str):
            raise InvalidActionParamsError("'category' must be a string or null")


PRODUCT_ADAPTER = Adapter(
    entity="product",
    actions=frozenset({"archive", "unarchive", "set_category"}),
    load=_load_products,
    summarise=_summarise_product,
    blocker=_product_blocker,
    apply=_apply_product,
    valid_params=_validate_product_params,
)


# ---------------------------------------------------------------------------
# Invoice adapter (mark_void)
# ---------------------------------------------------------------------------


async def _load_invoices(session: AsyncSession, ids: list[uuid.UUID]) -> list[Invoice]:
    if not ids:
        return []
    return list((await session.execute(select(Invoice).where(Invoice.id.in_(ids)))).scalars().all())


def _summarise_invoice(inv: Invoice) -> dict[str, Any]:
    return {
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "state": inv.state.value,
        "total_amount": str(inv.total_amount),
    }


async def _invoice_blocker(session: AsyncSession, inv: Invoice, action: str) -> str | None:
    _ = session
    if action == "mark_void":
        if inv.state == InvoiceState.VOID:
            return "already void"
        if inv.state != InvoiceState.DRAFT:
            return f"invoice is {inv.state.value}; only drafts can be voided here"
        return None
    return f"unsupported action {action!r}"


def _apply_invoice(inv: Invoice, action: str, params: dict[str, Any]) -> None:
    if action == "mark_void":
        inv.state = InvoiceState.VOID


INVOICE_ADAPTER = Adapter(
    entity="invoice",
    actions=frozenset({"mark_void"}),
    load=_load_invoices,
    summarise=_summarise_invoice,
    blocker=_invoice_blocker,
    apply=_apply_invoice,
)


# ---------------------------------------------------------------------------
# Bill adapter
# ---------------------------------------------------------------------------


async def _load_bills(session: AsyncSession, ids: list[uuid.UUID]) -> list[Bill]:
    if not ids:
        return []
    return list((await session.execute(select(Bill).where(Bill.id.in_(ids)))).scalars().all())


def _summarise_bill(b: Bill) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "bill_number": b.bill_number,
        "state": b.state.value,
        "total_amount": str(b.total_amount),
    }


async def _bill_blocker(session: AsyncSession, b: Bill, action: str) -> str | None:
    _ = session
    if action == "mark_void":
        if b.state == BillState.VOID:
            return "already void"
        if b.state != BillState.DRAFT:
            return f"bill is {b.state.value}; only drafts can be voided here"
        return None
    return f"unsupported action {action!r}"


def _apply_bill(b: Bill, action: str, params: dict[str, Any]) -> None:
    if action == "mark_void":
        b.state = BillState.VOID


BILL_ADAPTER = Adapter(
    entity="bill",
    actions=frozenset({"mark_void"}),
    load=_load_bills,
    summarise=_summarise_bill,
    blocker=_bill_blocker,
    apply=_apply_bill,
)


ADAPTERS: dict[str, Adapter] = {
    a.entity: a
    for a in (
        CUSTOMER_ADAPTER,
        VENDOR_ADAPTER,
        PRODUCT_ADAPTER,
        INVOICE_ADAPTER,
        BILL_ADAPTER,
    )
}


def get_adapter(entity: str) -> Adapter:
    try:
        return ADAPTERS[entity]
    except KeyError as exc:
        raise UnknownEntityError(
            f"unknown entity {entity!r}; expected one of {sorted(ADAPTERS)}"
        ) from exc


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def _validate(adapter: Adapter, action: str, params: dict[str, Any]) -> None:
    if action not in adapter.actions:
        raise UnknownActionError(
            f"action {action!r} not supported for {adapter.entity!r}; "
            f"expected one of {sorted(adapter.actions)}"
        )
    adapter.valid_params(action, params)


async def preview(
    *,
    session: AsyncSession,
    entity: str,
    ids: list[uuid.UUID],
    action: str,
    params: dict[str, Any] | None = None,
) -> BatchPreview:
    params = params or {}
    adapter = get_adapter(entity)
    _validate(adapter, action, params)

    rows = await adapter.load(session, ids)
    blockers: list[Blocker] = []
    for row in rows:
        reason = await adapter.blocker(session, row, action)
        if reason is not None:
            blockers.append(Blocker(id=row.id, reason=reason))

    sample = [adapter.summarise(r) for r in rows[:10]]
    return BatchPreview(
        entity=entity,
        action=action,
        matched_count=len(rows),
        sample=sample,
        blockers=blockers,
    )


async def commit(
    *,
    session: AsyncSession,
    entity: str,
    ids: list[uuid.UUID],
    action: str,
    actor_user_id: uuid.UUID | None,
    params: dict[str, Any] | None = None,
) -> BatchResult:
    params = params or {}
    adapter = get_adapter(entity)
    _validate(adapter, action, params)

    rows = await adapter.load(session, ids)
    blockers: list[Blocker] = []
    applied_ids: list[uuid.UUID] = []
    skipped_ids: list[uuid.UUID] = []

    for row in rows:
        reason = await adapter.blocker(session, row, action)
        if reason is not None:
            blockers.append(Blocker(id=row.id, reason=reason))
            skipped_ids.append(row.id)
            continue
        adapter.apply(row, action, params)
        applied_ids.append(row.id)

    event = await event_store.append(
        EventCreate(
            type=batch_ops_events.TYPE_BATCH_COMMITTED,
            aggregate_type=batch_ops_events.AGGREGATE_TYPE,
            aggregate_id=uuid.uuid4(),
            payload={
                "entity": entity,
                "action": action,
                "applied_ids": [str(i) for i in applied_ids],
                "skipped_ids": [str(i) for i in skipped_ids],
                "params": params,
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )
    await session.flush()
    return BatchResult(
        entity=entity,
        action=action,
        applied=len(applied_ids),
        skipped=len(skipped_ids),
        audit_id=event.id,
        blockers=blockers,
    )


__all__ = [
    "ADAPTERS",
    "Adapter",
    "BatchOpsError",
    "BatchPreview",
    "BatchResult",
    "Blocker",
    "InvalidActionParamsError",
    "UnknownActionError",
    "UnknownEntityError",
    "commit",
    "get_adapter",
    "preview",
]
