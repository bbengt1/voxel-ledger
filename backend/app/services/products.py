"""Products catalog service (Phase 2.3).

Mirrors the materials-service pattern (Phase 2.1): every mutation appends
a typed ``catalog.*`` event via ``EventStore.append`` inside the same
transaction as the row write, so the wildcard audit-log projection picks
it up automatically.

SKU allocation
--------------
``create`` allocates a fresh ``PROD-YYYY-NNNN`` SKU via
``ReferenceNumberService.allocate("PROD", session=session)`` unless the
caller supplies one. Manual SKUs are accepted as-is; the unique index on
``product.sku`` catches collisions at the DB layer too, but we pre-check
for a friendlier 400.

``unit_cost_cached``
--------------------
Reserved for the Phase 2.4 BOM rollup. This service neither reads nor
writes the column. Created here as nullable; defaults to NULL.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import catalog as catalog_events
from app.models.product import Product
from app.schemas.events import EventCreate
from app.services import custom_fields as cf_service
from app.services import event_store
from app.services.reference_number import ReferenceNumberService


class ProductsServiceError(Exception):
    """Base class. Routers map to 400."""


class ProductNotFoundError(ProductsServiceError):
    pass


class DuplicateSkuError(ProductsServiceError):
    pass


class DuplicateUpcError(ProductsServiceError):
    pass


class InvalidCursorError(ProductsServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dec_to_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


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
            aggregate_type=catalog_events.PRODUCT_AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, product_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(product_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _sku_exists(session: AsyncSession, sku: str) -> bool:
    stmt = select(Product.id).where(Product.sku == sku)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _upc_exists(
    session: AsyncSession, upc: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    stmt = select(Product.id).where(Product.upc == upc)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    unit_price: Decimal,
    sku: str | None = None,
    upc: str | None = None,
    weight_grams: Decimal | None = None,
    category: str | None = None,
    actor_user_id: uuid.UUID | None,
    custom_fields: dict[str, Any] | None = None,
) -> Product:
    name = name.strip()
    description_norm = description.strip() if description else None
    if description_norm == "":
        description_norm = None
    category_norm = category.strip() if category else None
    if category_norm == "":
        category_norm = None
    upc_norm = upc.strip() if upc else None
    if upc_norm == "":
        upc_norm = None

    if sku is None:
        allocated_sku = await ReferenceNumberService.allocate("PROD", session=session)
    else:
        allocated_sku = sku.strip()
        if await _sku_exists(session, allocated_sku):
            raise DuplicateSkuError(f"sku {allocated_sku!r} already exists")

    if upc_norm is not None and await _upc_exists(session, upc_norm):
        raise DuplicateUpcError(f"upc {upc_norm!r} already exists")

    normalized_cf = await cf_service.validate_payload("product", custom_fields, session=session)

    product = Product(
        sku=allocated_sku,
        upc=upc_norm,
        name=name,
        description=description_norm,
        unit_price=unit_price,
        unit_cost_cached=None,
        weight_grams=weight_grams,
        category=category_norm,
        is_archived=False,
        custom_fields=normalized_cf,
    )
    session.add(product)
    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_PRODUCT_CREATED,
        aggregate_id=product.id,
        payload={
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "unit_price": _dec_to_str(product.unit_price),
            "category": product.category,
        },
        actor_user_id=actor_user_id,
    )
    return product


async def get(session: AsyncSession, product_id: uuid.UUID) -> Product:
    stmt = select(Product).where(Product.id == product_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ProductNotFoundError(str(product_id))
    return row


async def lookup_by_code(session: AsyncSession, code: str) -> Product:
    """Lookup tries SKU first, then UPC. Both are indexed for sub-500ms."""
    code = code.strip()
    stmt = select(Product).where(Product.sku == code)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row
    stmt = select(Product).where(Product.upc == code)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ProductNotFoundError(f"no product with code {code!r}")
    return row


_EDITABLE_FIELDS = (
    "sku",
    "upc",
    "name",
    "description",
    "unit_price",
    "weight_grams",
    "category",
)


_NULLABLE_TEXT_FIELDS = frozenset({"upc", "description", "category"})


async def update(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    custom_fields: dict[str, Any] | None = None,
) -> Product:
    target = await get(session, product_id)

    if custom_fields is not None:
        target.custom_fields = await cf_service.validate_payload(
            "product", custom_fields, session=session
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    new_unit_price: Decimal | None = None
    old_unit_price: Decimal | None = None

    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = None if field in _NULLABLE_TEXT_FIELDS and stripped == "" else stripped
        current = getattr(target, field)
        if current == new_value:
            continue
        # SKU / UPC uniqueness checks before mutating.
        if field == "sku" and new_value is not None and await _sku_exists(session, new_value):
            raise DuplicateSkuError(f"sku {new_value!r} already exists")
        if (
            field == "upc"
            and new_value is not None
            and await _upc_exists(session, new_value, exclude_id=target.id)
        ):
            raise DuplicateUpcError(f"upc {new_value!r} already exists")
        before[field] = _dec_to_str(current) if isinstance(current, Decimal) else current
        after[field] = _dec_to_str(new_value) if isinstance(new_value, Decimal) else new_value
        if field == "unit_price":
            old_unit_price = current if isinstance(current, Decimal) else Decimal(str(current))
            new_unit_price = (
                new_value if isinstance(new_value, Decimal) else Decimal(str(new_value))
            )
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_PRODUCT_UPDATED,
        aggregate_id=target.id,
        payload={
            "product_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    if new_unit_price is not None and old_unit_price is not None:
        await _emit(
            session,
            event_type=catalog_events.TYPE_PRODUCT_PRICE_CHANGED,
            aggregate_id=target.id,
            payload={
                "product_id": str(target.id),
                "old_price": _dec_to_str(old_unit_price),
                "new_price": _dec_to_str(new_unit_price),
            },
            actor_user_id=actor_user_id,
        )
    return target


async def archive(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Product:
    target = await get(session, product_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_PRODUCT_ARCHIVED,
        aggregate_id=target.id,
        payload={"product_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Product:
    target = await get(session, product_id)
    if not target.is_archived:
        return target
    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_PRODUCT_UNARCHIVED,
        aggregate_id=target.id,
        payload={"product_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class ProductPage:
    items: list[Product]
    next_cursor: str | None


async def list_products(
    session: AsyncSession,
    *,
    search: str | None = None,
    category: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> ProductPage:
    stmt = select(Product)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Product.name).like(pattern),
                func.lower(Product.sku).like(pattern),
                func.lower(Product.upc).like(pattern),
            )
        )
    if category is not None:
        stmt = stmt.where(Product.category == category)
    if is_archived is not None:
        stmt = stmt.where(Product.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Product.created_at < anchor_ts,
                and_(Product.created_at == anchor_ts, Product.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Product.created_at), desc(Product.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return ProductPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "DuplicateSkuError",
    "DuplicateUpcError",
    "InvalidCursorError",
    "ProductNotFoundError",
    "ProductPage",
    "ProductsServiceError",
    "archive",
    "create",
    "get",
    "list_products",
    "lookup_by_code",
    "unarchive",
    "update",
]
