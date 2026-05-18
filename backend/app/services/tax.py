"""Tax-profile service (Phase 9.5, #157).

CRUD over ``tax_profile`` + ``tax_rate`` plus pure helpers for line/
invoice tax computation. The compute helpers do NOT touch the DB; they
take a list of ``TaxRate`` rows + a subtotal and return per-rate
amounts. The invoice service composes these into per-rate Cr lines in
the issue-time journal entry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import asc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import tax as tax_events
from app.models.account import Account
from app.models.customer import Customer
from app.models.invoice import InvoiceItem
from app.models.tax_profile import TaxProfile, TaxRate
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TaxServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class TaxProfileNotFoundError(TaxServiceError):
    """Mapped to 404."""


class TaxRateNotFoundError(TaxServiceError):
    """Mapped to 404."""


class DuplicateTaxProfileError(TaxServiceError):
    """``code`` collides with another row."""


class InvalidTaxProfileError(TaxServiceError):
    """Field-level validation (bad account type, bad rate, etc.)."""


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
# Event emission
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


async def _validate_liability_account(session: AsyncSession, account_id: uuid.UUID) -> None:
    row = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise InvalidTaxProfileError(f"liability_account_id {account_id} does not exist")
    if str(row.type) != "liability":
        raise InvalidTaxProfileError(
            f"liability_account_id {account_id} must be type=liability " f"(got {row.type!r})"
        )


# ---------------------------------------------------------------------------
# Pure compute helpers (no DB)
# ---------------------------------------------------------------------------


def compute_line_tax(
    *,
    line_subtotal: Decimal,
    rates: list[TaxRate],
) -> list[tuple[uuid.UUID, Decimal]]:
    """Return ``[(rate_id, amount), ...]`` in ordinal order.

    For each rate (sorted by ordinal):
      * if ``compound_on_previous`` is True, base = subtotal + sum of
        previous rate amounts.
      * else base = subtotal (flat).

    Each amount is quantized to 0.000001. Caller can sum the second
    column for the total line tax.
    """
    subtotal = _q(line_subtotal)
    out: list[tuple[uuid.UUID, Decimal]] = []
    running_sum = _ZERO
    for rate in sorted(rates, key=lambda r: r.ordinal):
        base = subtotal + running_sum if rate.compound_on_previous else subtotal
        amount = _q(base * Decimal(str(rate.rate)))
        out.append((rate.id, amount))
        running_sum += amount
    return out


def compute_invoice_tax(*, invoice: Any) -> dict[uuid.UUID, Decimal]:
    """Aggregate line tax across the invoice — rate_id -> total amount.

    The caller is responsible for having resolved each line's
    ``tax_profile_id`` already (the line carries the profile + the
    profile's rates are eagerly loaded). Lines without a profile
    contribute nothing.
    """
    totals: dict[uuid.UUID, Decimal] = {}
    for line in invoice.items:
        profile = getattr(line, "_resolved_tax_profile", None)
        if profile is None:
            continue
        line_subtotal = _q(line.extended_amount)
        for rate_id, amount in compute_line_tax(
            line_subtotal=line_subtotal, rates=list(profile.rates)
        ):
            totals[rate_id] = totals.get(rate_id, _ZERO) + amount
    return {rid: _q(v) for rid, v in totals.items()}


async def resolve_profile_for_invoice_line(
    session: AsyncSession,
    *,
    line: InvoiceItem,
    customer: Customer,
) -> TaxProfile | None:
    """Resolution chain (line override -> customer default -> none).

    Channel default + setting fallback are reserved for future phases.
    Returns the loaded profile with rates eager-loaded, or ``None``.
    """
    profile_id = line.tax_profile_id or customer.tax_profile_id
    if profile_id is None:
        return None
    stmt = (
        select(TaxProfile)
        .where(TaxProfile.id == profile_id)
        .options(selectinload(TaxProfile.rates))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD: profiles
# ---------------------------------------------------------------------------


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> TaxProfile:
    stmt = (
        select(TaxProfile)
        .where(TaxProfile.id == profile_id)
        .options(selectinload(TaxProfile.rates))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise TaxProfileNotFoundError(str(profile_id))
    return row


async def create_profile(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    jurisdiction: str,
    is_reverse_charge: bool = False,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> TaxProfile:
    code = code.strip()
    name = name.strip()
    jurisdiction = jurisdiction.strip()
    if not code:
        raise InvalidTaxProfileError("code is required")
    if not name:
        raise InvalidTaxProfileError("name is required")
    if not jurisdiction:
        raise InvalidTaxProfileError("jurisdiction is required")

    notes_clean = notes.strip() if isinstance(notes, str) else None
    if notes_clean == "":
        notes_clean = None

    profile = TaxProfile(
        code=code,
        name=name,
        jurisdiction=jurisdiction,
        is_reverse_charge=is_reverse_charge,
        notes=notes_clean,
        is_active=True,
        created_by_user_id=actor_user_id,
    )
    session.add(profile)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise DuplicateTaxProfileError(f"tax profile with code={code!r} already exists") from exc

    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_PROFILE_CREATED,
        aggregate_type=tax_events.AGGREGATE_TYPE_TAX_PROFILE,
        aggregate_id=profile.id,
        payload={
            "tax_profile_id": str(profile.id),
            "code": profile.code,
            "name": profile.name,
            "jurisdiction": profile.jurisdiction,
            "is_reverse_charge": profile.is_reverse_charge,
            "is_active": profile.is_active,
            "notes": profile.notes,
        },
        actor_user_id=actor_user_id,
    )
    return profile


_PROFILE_EDITABLE_FIELDS = (
    "code",
    "name",
    "jurisdiction",
    "is_reverse_charge",
    "notes",
    "is_active",
)


def _serialize(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


async def update_profile(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> TaxProfile:
    target = await get_profile(session, profile_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _PROFILE_EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("code", "name", "jurisdiction") and new_value is not None:
            if not isinstance(new_value, str) or not new_value.strip():
                raise InvalidTaxProfileError(f"{field} must not be empty")
            new_value = new_value.strip()
        elif field == "notes" and isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = None if stripped == "" else stripped

        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = _serialize(current)
        after[field] = _serialize(new_value)
        setattr(target, field, new_value)

    if not before:
        return target

    try:
        await session.flush()
    except IntegrityError as exc:
        raise DuplicateTaxProfileError(f"another tax profile uses code={target.code!r}") from exc

    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_PROFILE_UPDATED,
        aggregate_type=tax_events.AGGREGATE_TYPE_TAX_PROFILE,
        aggregate_id=target.id,
        payload={
            "tax_profile_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive_profile(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> TaxProfile:
    target = await get_profile(session, profile_id)
    if not target.is_active:
        return target
    target.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_PROFILE_ARCHIVED,
        aggregate_type=tax_events.AGGREGATE_TYPE_TAX_PROFILE,
        aggregate_id=target.id,
        payload={
            "tax_profile_id": str(target.id),
            "code": target.code,
            "name": target.name,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def list_profiles(
    session: AsyncSession,
    *,
    active: bool | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[TaxProfile]:
    from sqlalchemy import func

    stmt = select(TaxProfile).options(selectinload(TaxProfile.rates))
    if active is not None:
        stmt = stmt.where(TaxProfile.is_active.is_(active))
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(TaxProfile.code).like(pattern),
                func.lower(TaxProfile.name).like(pattern),
                func.lower(TaxProfile.jurisdiction).like(pattern),
            )
        )
    stmt = stmt.order_by(asc(TaxProfile.code)).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# CRUD: rates
# ---------------------------------------------------------------------------


async def add_rate(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    ordinal: int,
    name: str,
    rate: Decimal | str | int | float,
    liability_account_id: uuid.UUID,
    compound_on_previous: bool = False,
    actor_user_id: uuid.UUID | None,
) -> TaxRate:
    profile = await get_profile(session, profile_id)
    name = name.strip()
    if not name:
        raise InvalidTaxProfileError("rate name is required")
    try:
        rate_dec = Decimal(str(rate))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidTaxProfileError(f"invalid rate: {rate!r}") from exc
    await _validate_liability_account(session, liability_account_id)

    new_rate = TaxRate(
        profile_id=profile.id,
        ordinal=int(ordinal),
        name=name,
        rate=rate_dec,
        liability_account_id=liability_account_id,
        compound_on_previous=compound_on_previous,
    )
    session.add(new_rate)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidTaxProfileError(
            f"rate ordinal {ordinal} already exists on profile {profile_id}"
        ) from exc

    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_RATE_CREATED,
        aggregate_type=tax_events.AGGREGATE_TYPE_TAX_RATE,
        aggregate_id=new_rate.id,
        payload={
            "tax_rate_id": str(new_rate.id),
            "profile_id": str(new_rate.profile_id),
            "ordinal": new_rate.ordinal,
            "name": new_rate.name,
            "rate": str(new_rate.rate),
            "compound_on_previous": new_rate.compound_on_previous,
            "liability_account_id": str(new_rate.liability_account_id),
        },
        actor_user_id=actor_user_id,
    )
    return new_rate


_RATE_EDITABLE_FIELDS = (
    "ordinal",
    "name",
    "rate",
    "liability_account_id",
    "compound_on_previous",
)


async def _get_rate(session: AsyncSession, rate_id: uuid.UUID) -> TaxRate:
    row = (await session.execute(select(TaxRate).where(TaxRate.id == rate_id))).scalar_one_or_none()
    if row is None:
        raise TaxRateNotFoundError(str(rate_id))
    return row


async def update_rate(
    session: AsyncSession,
    *,
    rate_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> TaxRate:
    target = await _get_rate(session, rate_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _RATE_EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "name" and new_value is not None:
            if not isinstance(new_value, str) or not new_value.strip():
                raise InvalidTaxProfileError("rate name is required")
            new_value = new_value.strip()
        if field == "rate" and new_value is not None:
            try:
                new_value = Decimal(str(new_value))
            except (ArithmeticError, ValueError) as exc:
                raise InvalidTaxProfileError(f"invalid rate: {new_value!r}") from exc
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = _serialize(current)
        after[field] = _serialize(new_value)
        setattr(target, field, new_value)

    if not before:
        return target

    if "liability_account_id" in before:
        await _validate_liability_account(session, target.liability_account_id)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidTaxProfileError(
            f"rate ordinal {target.ordinal} collides on profile {target.profile_id}"
        ) from exc

    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_RATE_UPDATED,
        aggregate_type=tax_events.AGGREGATE_TYPE_TAX_RATE,
        aggregate_id=target.id,
        payload={
            "tax_rate_id": str(target.id),
            "profile_id": str(target.profile_id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def remove_rate(
    session: AsyncSession,
    *,
    rate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    target = await _get_rate(session, rate_id)
    payload = {
        "tax_rate_id": str(target.id),
        "profile_id": str(target.profile_id),
        "ordinal": target.ordinal,
    }
    await session.delete(target)
    await session.flush()
    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_RATE_REMOVED,
        aggregate_type=tax_events.AGGREGATE_TYPE_TAX_RATE,
        aggregate_id=uuid.UUID(payload["tax_rate_id"]),
        payload=payload,
        actor_user_id=actor_user_id,
    )


__all__ = [
    "DuplicateTaxProfileError",
    "InvalidTaxProfileError",
    "TaxProfileNotFoundError",
    "TaxRateNotFoundError",
    "TaxServiceError",
    "add_rate",
    "archive_profile",
    "compute_invoice_tax",
    "compute_line_tax",
    "create_profile",
    "get_profile",
    "list_profiles",
    "remove_rate",
    "resolve_profile_for_invoice_line",
    "update_profile",
    "update_rate",
]
