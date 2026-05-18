"""Fixed assets service (Phase 9.1, #153).

Covers tangible + intangible assets. The keystone operation is
:func:`acquire` — it allocates an ``ASSET-YYYY-NNNN`` reference,
inserts the row, posts a balanced JE (Dr Asset / Cr Bank-or-AP), and
emits ``acc.AssetAcquired`` ALL INSIDE THE SAME DB TRANSACTION. The
router commits.

Acquisition contra-side rules
-----------------------------
* Cash/Bank acquisition: ``contra_account_id`` MUST be an asset
  account (the Bank). A fresh JE is posted Dr Asset / Cr Bank for
  ``acquisition_cost``.
* Bill-funded acquisition (``acquisition_bill_id`` set): the bill's
  posted JE already did Dr Asset / Cr AP — Phase 8.2 routes the
  expense leg through ``line.expense_account_id_override``, so the
  operator must have set the override to the asset account on at
  least one line summing to ``acquisition_cost``. In that path we
  DO NOT post a new JE; we stamp ``posting_journal_entry_id`` with
  the bill's existing JE id. The bill must be ``issued`` (or any
  state after).

Account-type validation
-----------------------
* ``asset_account_id``: type=``asset``.
* ``accumulated_depreciation_account_id``: type=``asset`` (contra-asset).
  The Account ORM doesn't carry an ``is_contra`` flag today so we can
  only check the type column.
* ``depreciation_expense_account_id``: type=``expense``.
* ``contra_account_id`` (cash path): type=``asset`` or ``liability``.

Update rules
------------
:func:`update` accepts only metadata fields (``name``, ``notes``,
``serial_number``, ``vendor_id``). Once any depreciation has been
posted (Phase 9.3 will land that table), cost / life / method /
account changes will be hard-blocked. For #9.1 we just accept the
metadata patch.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting_assets as asset_events
from app.models.account import Account, AccountType
from app.models.bill import Bill, BillItem, BillState
from app.models.fixed_asset import (
    DepreciationMethod,
    FixedAsset,
    FixedAssetClass,
    FixedAssetKind,
    FixedAssetState,
)
from app.models.journal_entry import JournalEntry
from app.models.vendor import Vendor
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.reference_number import ReferenceNumberService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FixedAssetServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class FixedAssetNotFoundError(FixedAssetServiceError):
    """Mapped to 404."""


class InvalidFixedAssetInputError(FixedAssetServiceError):
    """Validation failure (bad amounts, missing fields, etc.)."""


class InvalidAccountTypeError(FixedAssetServiceError):
    """One of the supplied account_ids is the wrong COA type."""


class FixedAssetAccountNotFoundError(FixedAssetServiceError):
    """A referenced account_id doesn't exist."""


class InvalidAcquisitionBillError(FixedAssetServiceError):
    """The supplied ``acquisition_bill_id`` is missing, not issued, or
    has no line routing the requested ``acquisition_cost`` to the
    asset account."""


class FixedAssetUpdateNotAllowedError(FixedAssetServiceError):
    """Tried to update a non-whitelisted field."""


class InvalidCursorError(FixedAssetServiceError):
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
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, asset_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(asset_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Events
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
            aggregate_type=asset_events.AGGREGATE_TYPE_FIXED_ASSET,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Account validation
# ---------------------------------------------------------------------------


async def _load_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    row = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise FixedAssetAccountNotFoundError(str(account_id))
    return row


def _ensure_account_type(
    account: Account,
    *,
    allowed: tuple[str, ...],
    role: str,
) -> None:
    actual = account.type.value if hasattr(account.type, "value") else account.type
    if actual not in allowed:
        raise InvalidAccountTypeError(
            f"account {account.code!r} has type {actual!r}; "
            f"expected one of {allowed} for {role}"
        )


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, asset_id: uuid.UUID) -> FixedAsset:
    row = (
        await session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one_or_none()
    if row is None:
        raise FixedAssetNotFoundError(str(asset_id))
    return row


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _created_payload(asset: FixedAsset) -> dict[str, Any]:
    return {
        "asset_id": str(asset.id),
        "asset_number": asset.asset_number,
        "name": asset.name,
        "kind": _enum_value(asset.asset_kind),
        "asset_class": _enum_value(asset.asset_class),
        "acquisition_cost": str(asset.acquisition_cost),
        "useful_life_months": asset.useful_life_months,
    }


# ---------------------------------------------------------------------------
# acquire
# ---------------------------------------------------------------------------


async def acquire(
    *,
    session: AsyncSession,
    name: str,
    kind: str | FixedAssetKind,
    asset_class: str | FixedAssetClass,
    acquired_on: date,
    acquisition_cost: Decimal | str | int | float,
    salvage_value: Decimal | str | int | float = Decimal("0"),
    useful_life_months: int,
    depreciation_method: str | DepreciationMethod,
    asset_account_id: uuid.UUID,
    accumulated_depreciation_account_id: uuid.UUID,
    depreciation_expense_account_id: uuid.UUID,
    contra_account_id: uuid.UUID | None = None,
    serial_number: str | None = None,
    vendor_id: uuid.UUID | None = None,
    acquisition_bill_id: uuid.UUID | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> FixedAsset:
    """Allocate + insert + post + emit, all in the SAME DB transaction.

    The router commits. Any raise rolls back everything.

    When ``acquisition_bill_id`` is set the function does NOT post a
    fresh JE — the bill's existing posted JE already did Dr Asset / Cr
    AP via a line whose ``expense_account_id_override`` was the asset
    account. We validate that link and stamp the asset's
    ``posting_journal_entry_id`` with the bill's JE id.
    """

    # --- Normalize / validate scalars ---
    cost = _q(acquisition_cost)
    salvage = _q(salvage_value)
    if cost <= _ZERO:
        raise InvalidFixedAssetInputError("acquisition_cost must be > 0")
    if salvage < _ZERO:
        raise InvalidFixedAssetInputError("salvage_value must be >= 0")
    if useful_life_months <= 0:
        raise InvalidFixedAssetInputError("useful_life_months must be > 0")

    try:
        kind_e = FixedAssetKind(kind) if not isinstance(kind, FixedAssetKind) else kind
    except ValueError as exc:
        raise InvalidFixedAssetInputError(f"invalid kind: {kind!r}") from exc
    try:
        class_e = (
            FixedAssetClass(asset_class)
            if not isinstance(asset_class, FixedAssetClass)
            else asset_class
        )
    except ValueError as exc:
        raise InvalidFixedAssetInputError(f"invalid asset_class: {asset_class!r}") from exc
    try:
        method_e = (
            DepreciationMethod(depreciation_method)
            if not isinstance(depreciation_method, DepreciationMethod)
            else depreciation_method
        )
    except ValueError as exc:
        raise InvalidFixedAssetInputError(
            f"invalid depreciation_method: {depreciation_method!r}"
        ) from exc

    if not name or not name.strip():
        raise InvalidFixedAssetInputError("name is required")

    # --- Account validation ---
    asset_account = await _load_account(session, asset_account_id)
    _ensure_account_type(asset_account, allowed=(AccountType.ASSET.value,), role="asset_account_id")

    accum_account = await _load_account(session, accumulated_depreciation_account_id)
    _ensure_account_type(
        accum_account,
        allowed=(AccountType.ASSET.value,),
        role="accumulated_depreciation_account_id (contra-asset)",
    )

    dep_exp_account = await _load_account(session, depreciation_expense_account_id)
    _ensure_account_type(
        dep_exp_account,
        allowed=(AccountType.EXPENSE.value,),
        role="depreciation_expense_account_id",
    )

    # --- Vendor existence check (FK is RESTRICT but we want a clean 400) ---
    if vendor_id is not None:
        v = (
            await session.execute(select(Vendor).where(Vendor.id == vendor_id))
        ).scalar_one_or_none()
        if v is None:
            raise InvalidFixedAssetInputError(f"vendor not found: {vendor_id}")

    # --- Decide JE-posting path ---
    bill: Bill | None = None
    if acquisition_bill_id is not None:
        bill = (
            await session.execute(select(Bill).where(Bill.id == acquisition_bill_id))
        ).scalar_one_or_none()
        if bill is None:
            raise InvalidAcquisitionBillError(
                f"acquisition_bill_id {acquisition_bill_id} not found"
            )
        bill_state = bill.state.value if hasattr(bill.state, "value") else bill.state
        if bill_state == BillState.DRAFT.value:
            raise InvalidAcquisitionBillError(
                f"bill {bill.bill_number} is in state 'draft'; only issued bills "
                "can fund an asset acquisition"
            )
        if bill.posting_journal_entry_id is None:
            raise InvalidAcquisitionBillError(
                f"bill {bill.bill_number} has no posted journal entry; "
                "cannot fund an asset acquisition"
            )
        # Verify at least one bill line routes ``acquisition_cost`` to the
        # asset account via ``expense_account_id_override``.
        items_q = await session.execute(select(BillItem).where(BillItem.bill_id == bill.id))
        items = list(items_q.scalars().all())
        routed_total = sum(
            (
                _q(it.extended_amount)
                for it in items
                if it.expense_account_id_override == asset_account_id
            ),
            _ZERO,
        )
        if routed_total < cost:
            raise InvalidAcquisitionBillError(
                f"bill {bill.bill_number} routes only {routed_total} to the asset "
                f"account; need >= {cost} for this acquisition"
            )
        # If caller didn't pass a contra_account_id we infer it (vendor's
        # AP account on the bill); but it's optional — purely for event
        # payload traceability.
    else:
        if contra_account_id is None:
            raise InvalidFixedAssetInputError(
                "contra_account_id is required when acquisition_bill_id is null"
            )
        contra_account = await _load_account(session, contra_account_id)
        _ensure_account_type(
            contra_account,
            allowed=(AccountType.ASSET.value, AccountType.LIABILITY.value),
            role="contra_account_id (Bank or AP)",
        )

    # --- Allocate reference + insert row ---
    asset_number = await ReferenceNumberService.allocate("ASSET", session=session)

    asset = FixedAsset(
        asset_number=asset_number,
        name=name.strip(),
        asset_kind=kind_e,
        asset_class=class_e,
        acquired_on=acquired_on,
        acquisition_cost=cost,
        salvage_value=salvage,
        useful_life_months=useful_life_months,
        depreciation_method=method_e,
        asset_account_id=asset_account_id,
        accumulated_depreciation_account_id=accumulated_depreciation_account_id,
        depreciation_expense_account_id=depreciation_expense_account_id,
        serial_number=serial_number,
        vendor_id=vendor_id,
        acquisition_bill_id=acquisition_bill_id,
        state=FixedAssetState.ACTIVE,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(asset)
    await session.flush()

    await _emit(
        session,
        event_type=asset_events.TYPE_ASSET_CREATED,
        aggregate_id=asset.id,
        payload=_created_payload(asset),
        actor_user_id=actor_user_id,
    )

    # --- Post JE (or reuse bill's) ---
    je_id: uuid.UUID | None
    if bill is not None:
        je_id = bill.posting_journal_entry_id
        asset.posting_journal_entry_id = je_id
        contra_for_payload = contra_account_id
    else:
        posted_at = datetime.combine(acquired_on, datetime.min.time(), tzinfo=UTC)
        entry = await journal_service.post(
            journal_service.JournalEntryInput(
                description=f"Acquisition of asset {asset_number}",
                posted_at=posted_at,
                lines=[
                    journal_service.JournalLineInput(
                        account_id=asset_account_id,
                        debit=cost,
                        credit=_ZERO,
                        line_number=1,
                        memo=f"Dr asset for {asset_number}",
                    ),
                    journal_service.JournalLineInput(
                        account_id=contra_account_id,  # type: ignore[arg-type]
                        debit=_ZERO,
                        credit=cost,
                        line_number=2,
                        memo=f"Cr contra for {asset_number}",
                    ),
                ],
            ),
            session=session,
            actor_user_id=actor_user_id,
            _internal_skip_approval_check=True,
        )
        assert isinstance(entry, JournalEntry)
        je_id = entry.id
        asset.posting_journal_entry_id = je_id
        contra_for_payload = contra_account_id

    await session.flush()

    await _emit(
        session,
        event_type=asset_events.TYPE_ASSET_ACQUIRED,
        aggregate_id=asset.id,
        payload={
            "asset_id": str(asset.id),
            "asset_number": asset.asset_number,
            "acquisition_cost": str(cost),
            "journal_entry_id": str(je_id) if je_id is not None else None,
            "contra_account_id": (
                str(contra_for_payload) if contra_for_payload is not None else None
            ),
            "vendor_id": str(vendor_id) if vendor_id is not None else None,
            "acquisition_bill_id": (
                str(acquisition_bill_id) if acquisition_bill_id is not None else None
            ),
            "acquired_on": acquired_on.isoformat(),
        },
        actor_user_id=actor_user_id,
    )

    return asset


# ---------------------------------------------------------------------------
# update (metadata-only)
# ---------------------------------------------------------------------------

_UPDATABLE_FIELDS = ("name", "notes", "serial_number", "vendor_id")


def _serialize_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


async def update(
    *,
    session: AsyncSession,
    asset_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> FixedAsset:
    asset = await _load(session, asset_id)

    illegal = set(patch) - set(_UPDATABLE_FIELDS)
    if illegal:
        raise FixedAssetUpdateNotAllowedError(
            f"cannot update fields {sorted(illegal)} on fixed_asset; "
            "only name/notes/serial_number/vendor_id are mutable in #9.1 "
            "(cost/life/method/accounts will be blocked once any depreciation "
            "has been posted in #9.3)"
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _UPDATABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "vendor_id" and new_value is not None:
            v = (
                await session.execute(select(Vendor).where(Vendor.id == new_value))
            ).scalar_one_or_none()
            if v is None:
                raise InvalidFixedAssetInputError(f"vendor not found: {new_value}")
        current = getattr(asset, field)
        if current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(asset, field, new_value)

    if not before:
        return asset

    await session.flush()
    await _emit(
        session,
        event_type=asset_events.TYPE_ASSET_UPDATED,
        aggregate_id=asset.id,
        payload={
            "asset_id": str(asset.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return asset


# ---------------------------------------------------------------------------
# dispose (#9.4 stub)
# ---------------------------------------------------------------------------


async def dispose(*args, **kwargs) -> FixedAsset:
    """STUB. Will be implemented in Phase 9.4 (#155)."""
    raise NotImplementedError(
        "fixed_asset.dispose is reserved for Phase 9.4 (#155); not implemented in 9.1"
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, asset_id: uuid.UUID) -> FixedAsset:
    return await _load(session, asset_id)


@dataclass
class FixedAssetPage:
    items: list[FixedAsset]
    next_cursor: str | None


async def list_assets(
    session: AsyncSession,
    *,
    kind: str | None = None,
    asset_class: str | None = None,
    state: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> FixedAssetPage:
    stmt = select(FixedAsset)
    if kind is not None:
        try:
            stmt = stmt.where(FixedAsset.asset_kind == FixedAssetKind(kind))
        except ValueError as exc:
            raise FixedAssetServiceError(f"invalid kind filter: {kind!r}") from exc
    if asset_class is not None:
        try:
            stmt = stmt.where(FixedAsset.asset_class == FixedAssetClass(asset_class))
        except ValueError as exc:
            raise FixedAssetServiceError(f"invalid asset_class filter: {asset_class!r}") from exc
    if state is not None:
        try:
            stmt = stmt.where(FixedAsset.state == FixedAssetState(state))
        except ValueError as exc:
            raise FixedAssetServiceError(f"invalid state filter: {state!r}") from exc
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                FixedAsset.asset_number.ilike(like),
                FixedAsset.name.ilike(like),
                FixedAsset.serial_number.ilike(like),
            )
        )
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                FixedAsset.created_at < anchor_ts,
                and_(FixedAsset.created_at == anchor_ts, FixedAsset.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(FixedAsset.created_at), desc(FixedAsset.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return FixedAssetPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "FixedAssetAccountNotFoundError",
    "FixedAssetNotFoundError",
    "FixedAssetPage",
    "FixedAssetServiceError",
    "FixedAssetUpdateNotAllowedError",
    "InvalidAccountTypeError",
    "InvalidAcquisitionBillError",
    "InvalidCursorError",
    "InvalidFixedAssetInputError",
    "acquire",
    "dispose",
    "get",
    "list_assets",
    "update",
]
