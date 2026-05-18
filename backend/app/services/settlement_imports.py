"""Marketplace settlement import service (Phase 9.8, #160).

Parses a marketplace payout CSV into a ``settlement`` aggregate + N
``settlement_line`` rows. Three parsers ship in v1:

* ``parse_generic_csv`` — operator-supplied ``column_map`` (mirrors the
  Phase 8.9 bank-import generic pattern, lightly).
* ``parse_etsy_csv`` — thin Etsy adapter wrapping the generic parser
  with a preset column map. The schema mirrors Etsy's "Sales by date"
  / "Statement of deposits" downloads (worked example).
* ``parse_amazon_csv`` — placeholder that delegates to the generic
  parser via a documented column map; the real Amazon settlement
  report format lands in a follow-up.

Dedup
-----
The partial unique index on ``(settlement_id, external_txn_id) WHERE
external_txn_id IS NOT NULL`` protects against re-importing the same
row inside one settlement. On re-import of the same file we pre-check
the ``(settlement_id, external_txn_id)`` set in Python (mirrors Phase
8.9; works on SQLite + PG without dialect divergence). A defensive
``IntegrityError`` catch on flush is the belt-and-suspenders backstop.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import settlements as settlements_events
from app.models.account import Account
from app.models.sales_channel import SalesChannel
from app.models.settlement import (
    Settlement,
    SettlementLine,
    SettlementLineKind,
    SettlementLineState,
    SettlementState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reference_number import ReferenceNumberService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SettlementsServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class SettlementNotFoundError(SettlementsServiceError):
    """Mapped to 404."""


class InvalidSettlementFileError(SettlementsServiceError):
    """File could not be parsed."""


class InvalidSettlementStateError(SettlementsServiceError):
    """State transition not allowed."""


# ---------------------------------------------------------------------------
# Row dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SettlementLineRow:
    line_kind: str
    occurred_on: date
    description: str
    external_order_id: str | None
    external_txn_id: str | None
    amount: Decimal


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


_LINE_KIND_VALUES = {m.value for m in SettlementLineKind}


def _coerce_decimal(raw: str | None) -> Decimal:
    if raw is None:
        return Decimal("0")
    s = str(raw).strip()
    if s == "":
        return Decimal("0")
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise InvalidSettlementFileError(f"could not parse decimal from {raw!r}") from exc


def _parse_date(raw: str, fmt: str | None = None) -> date:
    s = raw.strip()
    if fmt:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError as exc:
            raise InvalidSettlementFileError(
                f"could not parse date {raw!r} with format {fmt!r}"
            ) from exc
    for candidate in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, candidate).date()
        except ValueError:
            continue
    raise InvalidSettlementFileError(f"could not parse date from {raw!r}")


def _lookup(row: dict[str, Any], key: str | None) -> str | None:
    if key is None:
        return None
    if key in row:
        val = row[key]
        return None if val is None else str(val)
    lower = key.lower()
    for k, v in row.items():
        if isinstance(k, str) and k.lower() == lower:
            return None if v is None else str(v)
    return None


def _normalize_kind(raw: str | None, default: str = "sale") -> str:
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in _LINE_KIND_VALUES:
        return s
    # Common synonyms
    if s in {"order", "sales", "transaction", "purchase"}:
        return "sale"
    if s in {"refunded", "return"}:
        return "refund"
    if s in {"fees", "commission", "marketplace fee"}:
        return "fee"
    if s in {"deposit", "transfer"}:
        return "payout"
    if s in {"tax_collected", "vat", "sales tax"}:
        return "tax"
    return "adjustment"


def parse_generic_csv(
    *,
    stream: io.TextIOBase,
    column_map: Mapping[str, str],
    date_format: str | None = None,
    delimiter: str = ",",
    default_line_kind: str = "sale",
) -> list[SettlementLineRow]:
    """Parse a marketplace CSV using an operator-supplied column map.

    ``column_map`` keys: ``date``, ``amount``, ``line_kind`` (optional —
    falls back to ``default_line_kind`` if absent), ``description``,
    ``external_order_id``, ``external_txn_id``.

    Empty rows (no date / no amount) are silently skipped — marketplace
    exports commonly have summary blanks at the bottom.
    """
    date_key = column_map.get("date")
    amount_key = column_map.get("amount")
    if not date_key:
        raise InvalidSettlementFileError("column_map.date is required")
    if not amount_key:
        raise InvalidSettlementFileError("column_map.amount is required")

    kind_key = column_map.get("line_kind")
    desc_key = column_map.get("description")
    order_key = column_map.get("external_order_id")
    txn_key = column_map.get("external_txn_id")

    reader = csv.DictReader(stream, delimiter=delimiter)
    rows: list[SettlementLineRow] = []
    for raw_row in reader:
        # csv.DictReader can yield None values when row has fewer fields
        # than header; treat that as empty.
        row = {k: (v if v is not None else "") for k, v in raw_row.items()}
        date_raw = _lookup(row, date_key)
        if not date_raw or date_raw.strip() == "":
            continue
        amount_raw = _lookup(row, amount_key)
        if amount_raw is None or amount_raw.strip() == "":
            continue
        occurred_on = _parse_date(date_raw, date_format)
        amount = _coerce_decimal(amount_raw)
        kind = _normalize_kind(_lookup(row, kind_key), default=default_line_kind)
        description = (_lookup(row, desc_key) or "").strip()
        order_id = _lookup(row, order_key)
        order_id = order_id.strip() if isinstance(order_id, str) and order_id.strip() else None
        txn_id = _lookup(row, txn_key)
        txn_id = txn_id.strip() if isinstance(txn_id, str) and txn_id.strip() else None
        rows.append(
            SettlementLineRow(
                line_kind=kind,
                occurred_on=occurred_on,
                description=description,
                external_order_id=order_id,
                external_txn_id=txn_id,
                amount=amount,
            )
        )
    return rows


# Etsy "Statement of deposits" / mixed-event CSV preset. Etsy's exports
# vary by report; this preset matches the schema used in the test
# fixture (Type,OrderID,TransactionID,Title,Date,Amount). Real-world
# operators tweak the map through the generic endpoint until we ship a
# dedicated Etsy report adapter.
ETSY_COLUMN_MAP: Mapping[str, str] = {
    "date": "Date",
    "amount": "Amount",
    "line_kind": "Type",
    "description": "Title",
    "external_order_id": "OrderID",
    "external_txn_id": "TransactionID",
}


def parse_etsy_csv(*, stream: io.TextIOBase) -> list[SettlementLineRow]:
    """Etsy-flavored adapter around :func:`parse_generic_csv`.

    Wraps ``ETSY_COLUMN_MAP``. Amazon / Shopify adapters land in
    follow-ups; for now operators with those marketplaces ship through
    :func:`parse_generic_csv` with their own column map.
    """
    return parse_generic_csv(stream=stream, column_map=ETSY_COLUMN_MAP)


def parse_amazon_csv(*, stream: io.TextIOBase) -> list[SettlementLineRow]:
    """Amazon settlement report adapter — follow-up.

    Amazon's settlement-report schema has variant headers across regions
    + report types. The full mapping lands in a follow-up; for now this
    stub delegates to :func:`parse_generic_csv` using a best-guess
    Amazon column map. Operators should prefer :func:`parse_generic_csv`
    with their own mapping until a dedicated adapter ships.
    """
    column_map = {
        "date": "posted-date",
        "amount": "amount",
        "line_kind": "transaction-type",
        "description": "description",
        "external_order_id": "order-id",
        "external_txn_id": "transaction-id",
    }
    return parse_generic_csv(stream=stream, column_map=column_map)


# ---------------------------------------------------------------------------
# Event emission
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
            aggregate_type=settlements_events.AGGREGATE_TYPE_SETTLEMENT,
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


async def _load_channel(session: AsyncSession, channel_id: uuid.UUID) -> SalesChannel:
    row = (
        await session.execute(select(SalesChannel).where(SalesChannel.id == channel_id))
    ).scalar_one_or_none()
    if row is None:
        raise InvalidSettlementFileError(f"sales channel {channel_id} not found")
    return row


async def _load_payout_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidSettlementFileError(f"payout account {account_id} not found")
    return acct


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


def _compute_totals(rows: list[SettlementLineRow]) -> dict[str, Decimal]:
    """Compute the five header totals from parsed rows.

    * ``gross_amount`` = sum of positive ``sale`` line amounts
    * ``fee_amount`` = ``abs(sum of fee lines)``
    * ``refund_amount`` = ``abs(sum of refund lines)``
    * ``adjustment_amount`` = sum of adjustment lines (signed)
    * ``payout_amount`` = ``gross - fees - refunds + adjustments``
    """
    gross = Decimal("0")
    fees = Decimal("0")
    refunds = Decimal("0")
    adjustments = Decimal("0")
    for r in rows:
        if r.line_kind == "sale" and r.amount > 0:
            gross += r.amount
        elif r.line_kind == "fee":
            fees += r.amount
        elif r.line_kind == "refund":
            refunds += r.amount
        elif r.line_kind == "adjustment":
            adjustments += r.amount
        # payout + tax lines are informational; payout is computed.
    payout = gross - abs(fees) - abs(refunds) + adjustments
    return {
        "gross_amount": gross,
        "fee_amount": abs(fees),
        "refund_amount": abs(refunds),
        "adjustment_amount": adjustments,
        "payout_amount": payout,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


_FORMAT_PARSERS = {
    "etsy": parse_etsy_csv,
    "amazon": parse_amazon_csv,
}


async def import_file(
    *,
    session: AsyncSession,
    channel_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    format_kind: str,
    period_start: date,
    period_end: date,
    payout_account_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    column_map: Mapping[str, str] | None = None,
) -> Settlement:
    """Parse the upload and persist a settlement + its lines.

    ``format_kind`` picks the parser: ``etsy``, ``amazon``, or
    ``generic``. ``generic`` requires ``column_map``.
    """
    await _load_channel(session, channel_id)
    await _load_payout_account(session, payout_account_id)

    text = file_bytes.decode("utf-8", errors="replace")
    stream = io.StringIO(text)

    fmt = format_kind.strip().lower()
    if fmt == "generic":
        if not column_map:
            raise InvalidSettlementFileError("column_map is required when format_kind='generic'")
        rows = parse_generic_csv(stream=stream, column_map=column_map)
    elif fmt in _FORMAT_PARSERS:
        rows = _FORMAT_PARSERS[fmt](stream=stream)
    else:
        raise InvalidSettlementFileError(f"unknown format_kind {format_kind!r}")

    if not rows:
        raise InvalidSettlementFileError("no rows parsed from upload")

    totals = _compute_totals(rows)

    settlement_number = await ReferenceNumberService.allocate("SETT", session=session)

    settlement = Settlement(
        settlement_number=settlement_number,
        channel_id=channel_id,
        period_start=period_start,
        period_end=period_end,
        gross_amount=totals["gross_amount"],
        fee_amount=totals["fee_amount"],
        refund_amount=totals["refund_amount"],
        adjustment_amount=totals["adjustment_amount"],
        payout_amount=totals["payout_amount"],
        payout_account_id=payout_account_id,
        filename=filename,
        imported_by_user_id=actor_user_id,
        state=SettlementState.IMPORTED,
    )
    session.add(settlement)
    await session.flush()

    # Pre-check dedup keys (mirror the Phase 8.9 bank-imports pattern).
    # Within a single import call the settlement is fresh, so collisions
    # only happen if the same external_txn_id appears twice in the
    # uploaded file itself — we silently drop the second occurrence.
    seen_txn_ids: set[str] = set()
    inserted_lines = 0
    for idx, r in enumerate(rows, start=1):
        if r.external_txn_id is not None:
            if r.external_txn_id in seen_txn_ids:
                continue
            seen_txn_ids.add(r.external_txn_id)
        line = SettlementLine(
            settlement_id=settlement.id,
            line_number=inserted_lines + 1,
            line_kind=SettlementLineKind(r.line_kind),
            occurred_on=r.occurred_on,
            description=r.description,
            external_order_id=r.external_order_id,
            external_txn_id=r.external_txn_id,
            amount=r.amount,
            state=SettlementLineState.UNMATCHED,
        )
        session.add(line)
        inserted_lines += 1
        _ = idx

    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidSettlementFileError(
            f"unexpected dedup conflict on settlement_line upload: {exc}"
        ) from exc

    await _emit(
        session,
        event_type=settlements_events.TYPE_SETTLEMENT_IMPORTED,
        aggregate_id=settlement.id,
        payload={
            "settlement_id": str(settlement.id),
            "settlement_number": settlement.settlement_number,
            "channel_id": str(settlement.channel_id),
            "period_end": settlement.period_end.isoformat(),
            "line_count": inserted_lines,
            "gross_amount": str(settlement.gross_amount),
            "fee_amount": str(settlement.fee_amount),
            "refund_amount": str(settlement.refund_amount),
            "adjustment_amount": str(settlement.adjustment_amount),
            "payout_amount": str(settlement.payout_amount),
        },
        actor_user_id=actor_user_id,
    )
    return settlement


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


async def cancel(
    *,
    session: AsyncSession,
    settlement_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Settlement:
    """Cancel a settlement that hasn't been posted yet.

    Only ``imported`` and ``matched`` states are cancellable. Posted
    settlements need the Phase 9.9 reversal flow.
    """
    row = await get(session, settlement_id)
    if row.state == SettlementState.CANCELLED:
        return row
    if row.state == SettlementState.POSTED:
        raise InvalidSettlementStateError(
            "cannot cancel a posted settlement; use Phase 9.9 reversal"
        )
    if row.state not in (SettlementState.IMPORTED, SettlementState.MATCHED):
        raise InvalidSettlementStateError(f"cannot cancel from state {row.state.value!r}")
    row.state = SettlementState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=settlements_events.TYPE_SETTLEMENT_CANCELLED,
        aggregate_id=row.id,
        payload={"settlement_id": str(row.id)},
        actor_user_id=actor_user_id,
    )
    return row


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, settlement_id: uuid.UUID) -> Settlement:
    row = (
        await session.execute(select(Settlement).where(Settlement.id == settlement_id))
    ).scalar_one_or_none()
    if row is None:
        raise SettlementNotFoundError(f"settlement {settlement_id} not found")
    return row


async def list_settlements(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID | None = None,
    state: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> tuple[list[Settlement], str | None]:
    stmt = select(Settlement)
    if channel_id is not None:
        stmt = stmt.where(Settlement.channel_id == channel_id)
    if state is not None:
        if state not in {m.value for m in SettlementState}:
            raise SettlementsServiceError(f"invalid state {state!r}")
        stmt = stmt.where(Settlement.state == SettlementState(state))
    if period_start is not None:
        stmt = stmt.where(Settlement.period_end >= period_start)
    if period_end is not None:
        stmt = stmt.where(Settlement.period_start <= period_end)
    if cursor is not None:
        try:
            cursor_ts_str, cursor_id_str = cursor.split("|", 1)
            cursor_ts = datetime.fromisoformat(cursor_ts_str)
            cursor_id = uuid.UUID(cursor_id_str)
        except Exception as exc:
            raise SettlementsServiceError(f"invalid cursor {cursor!r}") from exc
        stmt = stmt.where(
            or_(
                Settlement.imported_at < cursor_ts,
                and_(
                    Settlement.imported_at == cursor_ts,
                    Settlement.id < cursor_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(Settlement.imported_at), desc(Settlement.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = f"{last.imported_at.isoformat()}|{last.id}"
        rows = rows[:limit]
    return rows, next_cursor


async def list_lines(
    session: AsyncSession,
    *,
    settlement_id: uuid.UUID,
    state: str | None = None,
    limit: int = 500,
    cursor: str | None = None,
) -> tuple[list[SettlementLine], str | None]:
    stmt = select(SettlementLine).where(SettlementLine.settlement_id == settlement_id)
    if state is not None:
        if state not in {m.value for m in SettlementLineState}:
            raise SettlementsServiceError(f"invalid state {state!r}")
        stmt = stmt.where(SettlementLine.state == SettlementLineState(state))
    if cursor is not None:
        try:
            cursor_n = int(cursor)
        except ValueError as exc:
            raise SettlementsServiceError(f"invalid cursor {cursor!r}") from exc
        stmt = stmt.where(SettlementLine.line_number > cursor_n)
    stmt = stmt.order_by(asc(SettlementLine.line_number)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = str(last.line_number)
        rows = rows[:limit]
    return rows, next_cursor


__all__ = [
    "ETSY_COLUMN_MAP",
    "InvalidSettlementFileError",
    "InvalidSettlementStateError",
    "SettlementLineRow",
    "SettlementNotFoundError",
    "SettlementsServiceError",
    "cancel",
    "get",
    "import_file",
    "list_lines",
    "list_settlements",
    "parse_amazon_csv",
    "parse_etsy_csv",
    "parse_generic_csv",
]
