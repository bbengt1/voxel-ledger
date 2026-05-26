"""Printers service (Phase 5.1).

CRUD + archive lifecycle for the ``printer`` aggregate. Mirrors
``inventory_locations`` in shape — every mutation appends a typed
``production.Printer*`` event via ``EventStore.append`` inside the same
transaction as the row write.

**Secret handling.** ``moonraker_api_key`` is opaque. On update, the
diff payload uses ``"***"`` for both ``before`` and ``after`` so the
event log never contains the real key. Regression-tested.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, asc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import production as production_events
from app.models.printer import Printer, PrinterType
from app.schemas.events import EventCreate
from app.services import event_store

SECRET_SENTINEL = "***"


class PrintersServiceError(Exception):
    """Base class. Routers map to 400."""


class PrinterNotFoundError(PrintersServiceError):
    pass


class DuplicatePrinterError(PrintersServiceError):
    pass


class InvalidCursorError(PrintersServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
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
            aggregate_type=production_events.AGGREGATE_TYPE_PRINTER,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(slug: str, printer_id: uuid.UUID) -> str:
    raw = json.dumps({"s": slug, "i": str(printer_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return decoded["s"], uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


def _coerce_type(value: str | PrinterType) -> PrinterType:
    if isinstance(value, PrinterType):
        return value
    try:
        return PrinterType(value)
    except ValueError as exc:
        raise PrintersServiceError(f"invalid printer_type: {value!r}") from exc


async def _find_active_duplicate(
    session: AsyncSession,
    *,
    slug: str,
    exclude_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    stmt = select(Printer.id).where(Printer.slug == slug).where(Printer.is_archived.is_(False))
    if exclude_id is not None:
        stmt = stmt.where(Printer.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    printer_type: str | PrinterType,
    moonraker_url: str | None = None,
    moonraker_api_key: str | None = None,
    power_draw_watts: int | None = None,
    purchase_price: Decimal | None = None,
    salvage_value: Decimal | None = None,
    lifespan_years: int | None = None,
    annual_print_hours: int | None = None,
    preheat_minutes: int | None = None,
    preheat_power_watts: int | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> Printer:
    name = name.strip()
    slug = slug.strip()
    if not name:
        raise PrintersServiceError("name is required")
    if not slug:
        raise PrintersServiceError("slug is required")
    pt = _coerce_type(printer_type)

    moonraker_url_norm = (moonraker_url or "").strip() or None
    moonraker_api_key_norm = (moonraker_api_key or "").strip() or None
    notes_norm = (notes or "").strip() or None

    existing = await _find_active_duplicate(session, slug=slug)
    if existing is not None:
        raise DuplicatePrinterError(
            f"active printer with slug {slug!r} already exists ({existing})"
        )

    printer = Printer(
        name=name,
        slug=slug,
        printer_type=pt,
        moonraker_url=moonraker_url_norm,
        moonraker_api_key=moonraker_api_key_norm,
        power_draw_watts=power_draw_watts,
        purchase_price=purchase_price,
        salvage_value=salvage_value,
        lifespan_years=lifespan_years,
        annual_print_hours=annual_print_hours,
        preheat_minutes=preheat_minutes,
        preheat_power_watts=preheat_power_watts,
        notes=notes_norm,
        is_archived=False,
    )
    session.add(printer)
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_PRINTER_CREATED,
        aggregate_id=printer.id,
        payload={
            "printer_id": str(printer.id),
            "name": printer.name,
            "slug": printer.slug,
            "printer_type": pt.value,
        },
        actor_user_id=actor_user_id,
    )
    return printer


async def get(session: AsyncSession, printer_id: uuid.UUID) -> Printer:
    stmt = select(Printer).where(Printer.id == printer_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise PrinterNotFoundError(str(printer_id))
    return row


_EDITABLE_FIELDS = (
    "name",
    "slug",
    "printer_type",
    "moonraker_url",
    "moonraker_api_key",
    "power_draw_watts",
    "purchase_price",
    "salvage_value",
    "lifespan_years",
    "annual_print_hours",
    "preheat_minutes",
    "preheat_power_watts",
    "notes",
)


def _redact_for_diff(field: str, value: Any) -> Any:
    """Replace secret values with the sentinel for diff payloads."""
    if field == "moonraker_api_key" and value is not None:
        return SECRET_SENTINEL
    if isinstance(value, PrinterType):
        return value.value
    return value


async def update(
    session: AsyncSession,
    *,
    printer_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Printer:
    target = await get(session, printer_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "printer_type" and new_value is not None:
            new_value = _coerce_type(new_value)
        elif field in ("name", "slug"):
            if new_value is None:
                raise PrintersServiceError(f"{field} must not be null")
            stripped = new_value.strip()
            if not stripped:
                raise PrintersServiceError(f"{field} must not be empty")
            new_value = stripped
        elif field in ("moonraker_url", "moonraker_api_key", "notes") and isinstance(
            new_value, str
        ):
            stripped = new_value.strip()
            new_value = None if stripped == "" else stripped

        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = _redact_for_diff(field, current)
        after[field] = _redact_for_diff(field, new_value)
        setattr(target, field, new_value)

    if not before:
        return target

    if "slug" in before:
        existing = await _find_active_duplicate(session, slug=target.slug, exclude_id=target.id)
        if existing is not None:
            raise DuplicatePrinterError(f"another active printer uses slug {target.slug!r}")

    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_PRINTER_UPDATED,
        aggregate_id=target.id,
        payload={
            "printer_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    printer_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Printer:
    target = await get(session, printer_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=production_events.TYPE_PRINTER_ARCHIVED,
        aggregate_id=target.id,
        payload={"printer_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    printer_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Printer:
    target = await get(session, printer_id)
    if not target.is_archived:
        return target

    existing = await _find_active_duplicate(session, slug=target.slug, exclude_id=target.id)
    if existing is not None:
        raise DuplicatePrinterError(
            f"cannot unarchive: another active printer uses slug {target.slug!r}"
        )

    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=production_events.TYPE_PRINTER_UNARCHIVED,
        aggregate_id=target.id,
        payload={"printer_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class PrinterPage:
    items: list[Printer]
    next_cursor: str | None


async def list_printers(
    session: AsyncSession,
    *,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> PrinterPage:
    stmt = select(Printer)
    if is_archived is not None:
        stmt = stmt.where(Printer.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_slug, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Printer.slug > anchor_slug,
                and_(Printer.slug == anchor_slug, Printer.id > anchor_id),
            )
        )
    stmt = stmt.order_by(asc(Printer.slug), asc(Printer.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].slug, rows[-1].id) if (rows and has_more) else None
    return PrinterPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "DuplicatePrinterError",
    "InvalidCursorError",
    "PrinterNotFoundError",
    "PrinterPage",
    "PrintersServiceError",
    "SECRET_SENTINEL",
    "archive",
    "create",
    "get",
    "list_printers",
    "unarchive",
    "update",
]
