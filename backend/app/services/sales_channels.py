"""Sales channels service (Phase 6.1, #93).

A sales channel describes *where* a sale originates and *how its fees
work*. The aggregate carries:

* identity: ``name`` (unique) + ``slug`` (unique short token)
* shape: ``kind`` (pos / marketplace / direct_web / wholesale / other)
* fees: ``fee_model`` (none / flat / percent / percent_plus_flat) with
  ``fee_percent`` and ``fee_flat`` columns
* defaults: ``default_revenue_account_id`` and ``default_fee_account_id``
  — GL accounts the later sales-pathway phases will read by default
* operator hint: ``external_id_format_hint`` (e.g. ``^SHOP-\\d{10}$``)

Reference numbering convention (Phase 6.2 dependency)
-----------------------------------------------------
Sale orders authored in Phase 6.2 use the existing race-safe reference
allocator (issue #23 / ``app.services.reference_number``) with the
*single* prefix ``SO-`` regardless of channel. We considered hanging a
per-channel reference prefix off the ``sales_channel`` row (e.g.
``SO-ETSY-2026-0001``) and rejected it: the friction of carrying a
channel-aware prefix through every reporting / search / settlement path
outweighed any operator value. Channel attribution is a column on the
sale-order row, not the reference suffix.

Fee math
--------
``compute_fee(channel, gross_amount)`` is a pure function. All math runs
in ``Decimal`` to avoid float drift; interior values quantize to six
decimal places and return as a ``Decimal`` for the caller to round /
format. The fee matrix is:

    none              -> Decimal("0")
    flat              -> channel.fee_flat
    percent           -> gross_amount * channel.fee_percent
    percent_plus_flat -> gross_amount * channel.fee_percent + channel.fee_flat

If the channel's fee model says it needs a percent or flat that's
missing on the row, the helper raises ``InvalidFeeConfigurationError``
so callers get a loud signal instead of silently treating ``None`` as
zero.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import sales as sales_events
from app.models.sales_channel import (
    SalesChannel,
    SalesChannelFeeModel,
    SalesChannelKind,
)
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SalesChannelsServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class SalesChannelNotFoundError(SalesChannelsServiceError):
    """Mapped to 404."""


class DuplicateSalesChannelError(SalesChannelsServiceError):
    """Name or slug collision."""


class InvalidFeeConfigurationError(SalesChannelsServiceError):
    """``fee_model`` requires a value that's missing (or vice versa)."""


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_FEE_QUANTUM = Decimal("0.000001")  # 6 decimal places interior precision.


def _q(value: Decimal) -> Decimal:
    return value.quantize(_FEE_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pure fee calculator (used by Phase 6.2/6.3)
# ---------------------------------------------------------------------------


def compute_fee(channel: SalesChannel, gross_amount: Decimal) -> Decimal:
    """Compute the channel's fee for ``gross_amount``.

    Pure function — no DB, no clock. Returns a quantized ``Decimal``
    (6 fractional digits). Callers downstream usually re-quantize to
    USD cents before posting to the ledger.
    """
    if not isinstance(gross_amount, Decimal):
        gross_amount = Decimal(str(gross_amount))

    model = channel.fee_model
    if model == SalesChannelFeeModel.NONE:
        return _q(Decimal("0"))

    if model == SalesChannelFeeModel.FLAT:
        if channel.fee_flat is None:
            raise InvalidFeeConfigurationError("fee_model=flat requires fee_flat to be set")
        return _q(Decimal(channel.fee_flat))

    if model == SalesChannelFeeModel.PERCENT:
        if channel.fee_percent is None:
            raise InvalidFeeConfigurationError("fee_model=percent requires fee_percent to be set")
        return _q(gross_amount * Decimal(channel.fee_percent))

    if model == SalesChannelFeeModel.PERCENT_PLUS_FLAT:
        if channel.fee_percent is None or channel.fee_flat is None:
            raise InvalidFeeConfigurationError(
                "fee_model=percent_plus_flat requires both fee_percent and fee_flat"
            )
        return _q(gross_amount * Decimal(channel.fee_percent) + Decimal(channel.fee_flat))

    raise InvalidFeeConfigurationError(f"unknown fee_model: {model!r}")


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
            aggregate_type=sales_events.AGGREGATE_TYPE_SALES_CHANNEL,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_kind(value: str | SalesChannelKind) -> SalesChannelKind:
    if isinstance(value, SalesChannelKind):
        return value
    try:
        return SalesChannelKind(value)
    except ValueError as exc:
        raise SalesChannelsServiceError(f"invalid kind: {value!r}") from exc


def _coerce_fee_model(value: str | SalesChannelFeeModel) -> SalesChannelFeeModel:
    if isinstance(value, SalesChannelFeeModel):
        return value
    try:
        return SalesChannelFeeModel(value)
    except ValueError as exc:
        raise SalesChannelsServiceError(f"invalid fee_model: {value!r}") from exc


def _coerce_decimal(value: Decimal | str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_fee_config(
    fee_model: SalesChannelFeeModel,
    fee_percent: Decimal | None,
    fee_flat: Decimal | None,
) -> None:
    if fee_model == SalesChannelFeeModel.NONE:
        return
    if fee_model == SalesChannelFeeModel.FLAT and fee_flat is None:
        raise InvalidFeeConfigurationError("fee_model=flat requires fee_flat")
    if fee_model == SalesChannelFeeModel.PERCENT and fee_percent is None:
        raise InvalidFeeConfigurationError("fee_model=percent requires fee_percent")
    if fee_model == SalesChannelFeeModel.PERCENT_PLUS_FLAT and (
        fee_percent is None or fee_flat is None
    ):
        raise InvalidFeeConfigurationError(
            "fee_model=percent_plus_flat requires both fee_percent and fee_flat"
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def _find_duplicate(
    session: AsyncSession,
    *,
    name: str | None = None,
    slug: str | None = None,
    exclude_id: uuid.UUID | None = None,
) -> str | None:
    """Return a label of the conflicting field (``"name"`` or ``"slug"``)
    if a different row already uses ``name`` or ``slug``."""
    if name is not None:
        stmt = select(SalesChannel.id).where(SalesChannel.name == name)
        if exclude_id is not None:
            stmt = stmt.where(SalesChannel.id != exclude_id)
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            return "name"
    if slug is not None:
        stmt = select(SalesChannel.id).where(SalesChannel.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(SalesChannel.id != exclude_id)
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            return "slug"
    return None


async def get(session: AsyncSession, channel_id: uuid.UUID) -> SalesChannel:
    stmt = select(SalesChannel).where(SalesChannel.id == channel_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SalesChannelNotFoundError(str(channel_id))
    return row


async def create(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    kind: str | SalesChannelKind,
    fee_model: str | SalesChannelFeeModel,
    fee_percent: Decimal | str | int | float | None = None,
    fee_flat: Decimal | str | int | float | None = None,
    default_revenue_account_id: uuid.UUID | None = None,
    default_fee_account_id: uuid.UUID | None = None,
    tax_profile_id: uuid.UUID | None = None,
    external_id_format_hint: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> SalesChannel:
    name = name.strip()
    slug = slug.strip()
    if not name:
        raise SalesChannelsServiceError("name is required")
    if not slug:
        raise SalesChannelsServiceError("slug is required")

    kind_value = _coerce_kind(kind)
    fee_model_value = _coerce_fee_model(fee_model)
    fee_percent_dec = _coerce_decimal(fee_percent)
    fee_flat_dec = _coerce_decimal(fee_flat)

    _validate_fee_config(fee_model_value, fee_percent_dec, fee_flat_dec)

    conflict = await _find_duplicate(session, name=name, slug=slug)
    if conflict is not None:
        offending = name if conflict == "name" else slug
        raise DuplicateSalesChannelError(
            f"sales channel with {conflict}={offending!r} already exists"
        )

    hint = external_id_format_hint.strip() if external_id_format_hint else None
    if hint == "":
        hint = None

    channel = SalesChannel(
        name=name,
        slug=slug,
        kind=kind_value,
        fee_model=fee_model_value,
        fee_percent=fee_percent_dec,
        fee_flat=fee_flat_dec,
        is_active=True,
        default_revenue_account_id=default_revenue_account_id,
        default_fee_account_id=default_fee_account_id,
        tax_profile_id=tax_profile_id,
        external_id_format_hint=hint,
    )
    session.add(channel)
    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_SALES_CHANNEL_CREATED,
        aggregate_id=channel.id,
        payload={
            "sales_channel_id": str(channel.id),
            "name": channel.name,
            "slug": channel.slug,
            "kind": kind_value.value,
            "fee_model": fee_model_value.value,
            "fee_percent": str(fee_percent_dec) if fee_percent_dec is not None else None,
            "fee_flat": str(fee_flat_dec) if fee_flat_dec is not None else None,
            "default_revenue_account_id": (
                str(default_revenue_account_id) if default_revenue_account_id else None
            ),
            "default_fee_account_id": (
                str(default_fee_account_id) if default_fee_account_id else None
            ),
            "external_id_format_hint": hint,
        },
        actor_user_id=actor_user_id,
    )
    return channel


_EDITABLE_FIELDS = (
    "name",
    "slug",
    "kind",
    "fee_model",
    "fee_percent",
    "fee_flat",
    "default_revenue_account_id",
    "default_fee_account_id",
    "tax_profile_id",
    "external_id_format_hint",
)


def _serialize_field(field: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, SalesChannelKind | SalesChannelFeeModel):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def update(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> SalesChannel:
    target = await get(session, channel_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "kind" and new_value is not None:
            new_value = _coerce_kind(new_value)
        elif field == "fee_model" and new_value is not None:
            new_value = _coerce_fee_model(new_value)
        elif field in ("fee_percent", "fee_flat"):
            new_value = _coerce_decimal(new_value)
        elif field == "external_id_format_hint":
            if isinstance(new_value, str):
                stripped = new_value.strip()
                new_value = None if stripped == "" else stripped
        elif isinstance(new_value, str):
            stripped = new_value.strip()
            if not stripped:
                raise SalesChannelsServiceError(f"{field} must not be empty")
            new_value = stripped

        current = getattr(target, field)
        # Decimal equality across DB-loaded Decimal vs caller Decimal can
        # differ in scale; compare via str.
        if isinstance(current, Decimal) and isinstance(new_value, Decimal):
            if Decimal(current) == new_value:
                continue
        elif current == new_value:
            continue

        before[field] = _serialize_field(field, current)
        after[field] = _serialize_field(field, new_value)
        setattr(target, field, new_value)

    if not before:
        return target

    # Re-validate fee model + values after the merge.
    _validate_fee_config(target.fee_model, target.fee_percent, target.fee_flat)

    # Re-check uniqueness on changed identity fields.
    if "name" in before or "slug" in before:
        conflict = await _find_duplicate(
            session,
            name=target.name if "name" in before else None,
            slug=target.slug if "slug" in before else None,
            exclude_id=target.id,
        )
        if conflict is not None:
            raise DuplicateSalesChannelError(
                f"another sales channel uses {conflict}={getattr(target, conflict)!r}"
            )

    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_SALES_CHANNEL_UPDATED,
        aggregate_id=target.id,
        payload={
            "sales_channel_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> SalesChannel:
    target = await get(session, channel_id)
    if not target.is_active:
        return target
    target.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SALES_CHANNEL_ARCHIVED,
        aggregate_id=target.id,
        payload={"sales_channel_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> SalesChannel:
    target = await get(session, channel_id)
    if target.is_active:
        return target
    target.is_active = True
    await session.flush()
    await _emit(
        session,
        event_type=sales_events.TYPE_SALES_CHANNEL_UNARCHIVED,
        aggregate_id=target.id,
        payload={"sales_channel_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def list_channels(
    session: AsyncSession,
    *,
    active: bool | None = None,
) -> list[SalesChannel]:
    """Return all sales channels sorted by name.

    ``active`` filters to ``is_active`` rows when ``True`` and inactive
    when ``False``. Sales channels are a small, finite set (single
    digits to low double digits) so no pagination is needed.
    """
    stmt = select(SalesChannel)
    if active is not None:
        stmt = stmt.where(SalesChannel.is_active.is_(active))
    stmt = stmt.order_by(asc(SalesChannel.name))
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "DuplicateSalesChannelError",
    "InvalidFeeConfigurationError",
    "SalesChannelNotFoundError",
    "SalesChannelsServiceError",
    "archive",
    "compute_fee",
    "create",
    "get",
    "list_channels",
    "unarchive",
    "update",
]
