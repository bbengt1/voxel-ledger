"""Bank-import service (Phase 8.9, #136).

Three pure parser functions (``parse_csv`` / ``parse_ofx`` /
``canonical_hash``) plus async mapping CRUD and ``import_file`` driver.

Dedup
-----
The unique constraint on ``(account_id, external_hash)`` is the source of
truth for "have we seen this row before". The canonical hash mixes the
account, date, amount, description, and OFX FITID (when present) into a
deterministic sha256 hex digest. Rows that hash-collide are silently
skipped — counted into ``duplicate_count`` rather than raising.

OFX parser
----------
We hand-roll a minimal regex parser for the ``<STMTTRN>...</STMTTRN>``
subset. No external dep. This handles the 90% case for what a small
business operator pastes; richer files (multi-statement, SGML headers,
investment accounts) are explicitly out of scope.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import banking as banking_events
from app.models.account import Account
from app.models.bank import (
    BankAmountSign,
    BankImportFileKind,
    BankImportMapping,
    BankImportRun,
    BankTransaction,
    BankTransactionState,
)
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BankImportsServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class BankImportMappingNotFoundError(BankImportsServiceError):
    """Mapped to 404."""


class BankImportRunNotFoundError(BankImportsServiceError):
    """Mapped to 404."""


class InvalidBankImportFileError(BankImportsServiceError):
    """File could not be parsed at all (bad header, unreadable, etc.)."""


class InvalidBankImportMappingError(BankImportsServiceError):
    """Mapping fields fail validation."""


class DuplicateBankImportMappingError(BankImportsServiceError):
    """``(account_id, name)`` collides with another row."""


# ---------------------------------------------------------------------------
# Parsed row dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BankTransactionRow:
    occurred_on: date
    description: str
    memo: str | None
    amount: Decimal
    running_balance: Decimal | None
    fitid: str | None


# ---------------------------------------------------------------------------
# Canonical hash
# ---------------------------------------------------------------------------


def canonical_hash(
    *,
    account_id: uuid.UUID,
    occurred_on: date,
    amount: Decimal,
    description: str,
    fitid: str | None,
) -> str:
    """sha256 hex of a deterministic concatenation. FITID participates
    when present so OFX rows dedup stably across re-imports of the same
    statement."""
    canonical = f"{account_id}|{occurred_on.isoformat()}|{amount}|{description}|{fitid or ''}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def _coerce_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    # Strip $ and thousands separators; leave the sign / decimal alone.
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    # Parentheses = negative (accounting convention).
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"could not parse decimal from {raw!r}") from exc


def _parse_date(raw: str, fmt: str | None) -> date:
    s = raw.strip()
    if fmt:
        return datetime.strptime(s, fmt).date()
    # Best-effort fallbacks: ISO, MM/DD/YYYY, M/D/YYYY.
    for candidate in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, candidate).date()
        except ValueError:
            continue
    raise ValueError(f"could not parse date from {raw!r} (no date_format and no fallback matched)")


def _lookup(row: dict[str, Any], key: str | None) -> str | None:
    if key is None:
        return None
    if key in row:
        return row[key]
    # Case-insensitive fallback for casual operator maps.
    lower = key.lower()
    for k, v in row.items():
        if isinstance(k, str) and k.lower() == lower:
            return v
    return None


def parse_csv(
    *,
    stream: io.TextIOBase,
    mapping: BankImportMapping,
) -> list[BankTransactionRow]:
    """Pure: parses a CSV stream into a list of rows.

    Raises :class:`ValueError` on a bad row (unparseable date / amount).
    The caller decides whether to fail-fast or count and continue.
    """
    cmap: dict[str, Any] = dict(mapping.column_map or {})
    date_key = cmap.get("date")
    desc_key = cmap.get("description")
    amount_key = cmap.get("amount")
    debit_key = cmap.get("debit")
    credit_key = cmap.get("credit")
    inflow_key = cmap.get("inflow")
    outflow_key = cmap.get("outflow")
    balance_key = cmap.get("balance")
    memo_key = cmap.get("memo")

    if not date_key:
        raise ValueError("column_map.date is required for CSV mappings")
    if not desc_key:
        raise ValueError("column_map.description is required for CSV mappings")

    delim = mapping.delimiter or ","

    rows_out: list[BankTransactionRow] = []

    if mapping.has_header:
        reader: Iterable[dict[str, Any]] = csv.DictReader(stream, delimiter=delim)
    else:
        # Without a header, the column_map values are integer indices stringified.
        raw_reader = csv.reader(stream, delimiter=delim)

        def _index_rows() -> Iterable[dict[str, Any]]:
            for row in raw_reader:
                yield {str(i): v for i, v in enumerate(row)}

        reader = _index_rows()

    sign_mode = (
        mapping.amount_sign.value
        if isinstance(mapping.amount_sign, BankAmountSign)
        else str(mapping.amount_sign)
    )

    for row in reader:
        date_raw = _lookup(row, date_key)
        if date_raw is None or str(date_raw).strip() == "":
            # Blank trailing rows are common in bank exports; skip silently.
            continue
        occurred_on = _parse_date(str(date_raw), mapping.date_format)
        description = (_lookup(row, desc_key) or "").strip()
        memo = _lookup(row, memo_key) if memo_key else None
        memo_clean = memo.strip() if isinstance(memo, str) and memo.strip() else None
        balance = _coerce_decimal(_lookup(row, balance_key)) if balance_key else None

        amount: Decimal
        if sign_mode == BankAmountSign.SIGNED_AMOUNT.value:
            amount_val = _coerce_decimal(_lookup(row, amount_key))
            if amount_val is None:
                raise ValueError(f"missing amount in row {row!r}")
            amount = amount_val
        elif sign_mode == BankAmountSign.DEBIT_CREDIT_COLUMNS.value:
            debit = _coerce_decimal(_lookup(row, debit_key)) or Decimal("0")
            credit = _coerce_decimal(_lookup(row, credit_key)) or Decimal("0")
            # Credit = inflow (positive). Debit = outflow (negative).
            amount = credit - debit
        elif sign_mode == BankAmountSign.INFLOW_OUTFLOW.value:
            inflow = _coerce_decimal(_lookup(row, inflow_key)) or Decimal("0")
            outflow = _coerce_decimal(_lookup(row, outflow_key)) or Decimal("0")
            # Outflow column is unsigned; subtract it to make signed amount.
            amount = inflow - outflow
        else:
            raise ValueError(f"unknown amount_sign {sign_mode!r}")

        rows_out.append(
            BankTransactionRow(
                occurred_on=occurred_on,
                description=description,
                memo=memo_clean,
                amount=amount,
                running_balance=balance,
                fitid=None,
            )
        )

    return rows_out


# ---------------------------------------------------------------------------
# OFX parsing
# ---------------------------------------------------------------------------


_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL | re.IGNORECASE)


def _ofx_field(block: str, tag: str) -> str | None:
    pattern = rf"<{tag}>([^\r\n<]*)"
    m = re.search(pattern, block, re.IGNORECASE)
    if m is None:
        return None
    val = m.group(1).strip()
    return val or None


def _parse_ofx_date(raw: str) -> date:
    # DTPOSTED is YYYYMMDD[HHMMSS[.MSEC]][TZ]
    if len(raw) < 8:
        raise ValueError(f"DTPOSTED too short: {raw!r}")
    yr = int(raw[0:4])
    mo = int(raw[4:6])
    da = int(raw[6:8])
    return date(yr, mo, da)


def parse_ofx(*, stream: io.IOBase) -> list[BankTransactionRow]:
    """Pure: parses an OFX file's STMTTRN blocks. Hand-rolled subset; no
    external deps."""
    raw = stream.read()
    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw

    rows: list[BankTransactionRow] = []
    for m in _STMTTRN_RE.finditer(text):
        block = m.group(1)
        dt_raw = _ofx_field(block, "DTPOSTED")
        amount_raw = _ofx_field(block, "TRNAMT")
        if dt_raw is None or amount_raw is None:
            continue
        occurred_on = _parse_ofx_date(dt_raw)
        amount_val = _coerce_decimal(amount_raw)
        if amount_val is None:
            continue
        name = _ofx_field(block, "NAME") or ""
        memo = _ofx_field(block, "MEMO")
        fitid = _ofx_field(block, "FITID")
        rows.append(
            BankTransactionRow(
                occurred_on=occurred_on,
                description=name.strip(),
                memo=memo,
                amount=amount_val,
                running_balance=None,
                fitid=fitid,
            )
        )
    return rows


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
# Mapping CRUD
# ---------------------------------------------------------------------------


async def _validate_account(session: AsyncSession, account_id: uuid.UUID) -> None:
    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidBankImportMappingError(f"account {account_id} does not exist")


def _serialize_for_event(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, BankAmountSign | BankImportFileKind | BankTransactionState):
        return value.value
    return value


async def create_mapping(
    session: AsyncSession,
    *,
    name: str,
    account_id: uuid.UUID,
    file_kind: str,
    column_map: dict[str, Any] | None = None,
    date_format: str | None = None,
    delimiter: str = ",",
    has_header: bool = True,
    encoding: str = "utf-8",
    amount_sign: str,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> BankImportMapping:
    name_clean = name.strip()
    if not name_clean:
        raise BankImportsServiceError("name is required")
    if file_kind not in BankImportFileKind._value2member_map_:
        raise InvalidBankImportMappingError(f"invalid file_kind {file_kind!r}")
    if amount_sign not in BankAmountSign._value2member_map_:
        raise InvalidBankImportMappingError(f"invalid amount_sign {amount_sign!r}")
    await _validate_account(session, account_id)
    cmap = column_map or {}
    notes_clean = notes.strip() if isinstance(notes, str) and notes.strip() else None

    row = BankImportMapping(
        name=name_clean,
        account_id=account_id,
        file_kind=BankImportFileKind(file_kind),
        column_map=cmap,
        date_format=date_format,
        delimiter=delimiter or ",",
        has_header=has_header,
        encoding=encoding or "utf-8",
        amount_sign=BankAmountSign(amount_sign),
        is_active=True,
        notes=notes_clean,
        created_by_user_id=actor_user_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateBankImportMappingError(
            f"a mapping named {name_clean!r} already exists for account {account_id}"
        ) from exc

    await _emit(
        session,
        event_type=banking_events.TYPE_MAPPING_CREATED,
        aggregate_type=banking_events.AGGREGATE_TYPE_BANK_IMPORT_MAPPING,
        aggregate_id=row.id,
        payload={
            "mapping_id": str(row.id),
            "account_id": str(row.account_id),
            "name": row.name,
            "file_kind": row.file_kind.value,
            "amount_sign": row.amount_sign.value,
            "delimiter": row.delimiter,
            "has_header": row.has_header,
            "encoding": row.encoding,
            "date_format": row.date_format,
            "column_map": dict(row.column_map or {}),
            "notes": row.notes,
        },
        actor_user_id=actor_user_id,
    )
    return row


_MAPPING_EDITABLE = (
    "name",
    "column_map",
    "date_format",
    "delimiter",
    "has_header",
    "encoding",
    "amount_sign",
    "notes",
    "is_active",
)


async def get_mapping(session: AsyncSession, mapping_id: uuid.UUID) -> BankImportMapping:
    row = (
        await session.execute(select(BankImportMapping).where(BankImportMapping.id == mapping_id))
    ).scalar_one_or_none()
    if row is None:
        raise BankImportMappingNotFoundError(str(mapping_id))
    return row


async def update_mapping(
    session: AsyncSession,
    *,
    mapping_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> BankImportMapping:
    target = await get_mapping(session, mapping_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _MAPPING_EDITABLE:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "name" and new_value is not None:
            if not isinstance(new_value, str) or not new_value.strip():
                raise BankImportsServiceError("name must not be empty")
            new_value = new_value.strip()
        elif field == "notes":
            if isinstance(new_value, str):
                stripped = new_value.strip()
                new_value = stripped or None
        elif field == "amount_sign" and new_value is not None:
            if new_value not in BankAmountSign._value2member_map_:
                raise InvalidBankImportMappingError(f"invalid amount_sign {new_value!r}")
            new_value = BankAmountSign(new_value)
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = _serialize_for_event(current)
        after[field] = _serialize_for_event(new_value)
        setattr(target, field, new_value)

    if not before:
        return target

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateBankImportMappingError(
            f"another mapping uses name={target.name!r} for this account"
        ) from exc

    await _emit(
        session,
        event_type=banking_events.TYPE_MAPPING_UPDATED,
        aggregate_type=banking_events.AGGREGATE_TYPE_BANK_IMPORT_MAPPING,
        aggregate_id=target.id,
        payload={
            "mapping_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def deactivate_mapping(
    session: AsyncSession,
    *,
    mapping_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> BankImportMapping:
    target = await get_mapping(session, mapping_id)
    if not target.is_active:
        return target
    target.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=banking_events.TYPE_MAPPING_DEACTIVATED,
        aggregate_type=banking_events.AGGREGATE_TYPE_BANK_IMPORT_MAPPING,
        aggregate_id=target.id,
        payload={
            "mapping_id": str(target.id),
            "account_id": str(target.account_id),
            "name": target.name,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def list_mappings(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    limit: int = 200,
) -> list[BankImportMapping]:
    stmt = select(BankImportMapping)
    if account_id is not None:
        stmt = stmt.where(BankImportMapping.account_id == account_id)
    if not include_inactive:
        stmt = stmt.where(BankImportMapping.is_active.is_(True))
    stmt = stmt.order_by(asc(BankImportMapping.name)).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Import driver
# ---------------------------------------------------------------------------


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> BankImportRun:
    row = (
        await session.execute(select(BankImportRun).where(BankImportRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise BankImportRunNotFoundError(str(run_id))
    return row


async def import_file(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    filename: str,
    file_bytes: bytes,
    mapping_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
) -> BankImportRun:
    await _validate_account(session, account_id)

    mapping: BankImportMapping | None = None
    file_kind: BankImportFileKind
    if mapping_id is not None:
        mapping = await get_mapping(session, mapping_id)
        if mapping.account_id != account_id:
            raise InvalidBankImportFileError("mapping account does not match the requested account")
        if not mapping.is_active:
            raise InvalidBankImportFileError("mapping is deactivated")
        file_kind = mapping.file_kind
    else:
        # No mapping → treat as OFX. CSV without a mapping is rejected.
        file_kind = BankImportFileKind.OFX

    run = BankImportRun(
        account_id=account_id,
        mapping_id=mapping.id if mapping is not None else None,
        filename=filename,
        imported_by_user_id=actor_user_id,
        row_count=0,
        inserted_count=0,
        duplicate_count=0,
        error_count=0,
    )
    session.add(run)
    await session.flush()

    await _emit(
        session,
        event_type=banking_events.TYPE_IMPORT_RUN_STARTED,
        aggregate_type=banking_events.AGGREGATE_TYPE_BANK_IMPORT_RUN,
        aggregate_id=run.id,
        payload={
            "run_id": str(run.id),
            "account_id": str(run.account_id),
            "mapping_id": str(mapping.id) if mapping is not None else None,
            "filename": run.filename,
            "file_kind": file_kind.value,
        },
        actor_user_id=actor_user_id,
    )

    try:
        if file_kind == BankImportFileKind.OFX:
            rows = parse_ofx(stream=io.BytesIO(file_bytes))
        else:
            assert mapping is not None  # csv requires a mapping
            text_stream = io.StringIO(file_bytes.decode(mapping.encoding or "utf-8"))
            rows = parse_csv(stream=text_stream, mapping=mapping)
    except Exception as exc:
        await _emit(
            session,
            event_type=banking_events.TYPE_IMPORT_RUN_FAILED,
            aggregate_type=banking_events.AGGREGATE_TYPE_BANK_IMPORT_RUN,
            aggregate_id=run.id,
            payload={
                "run_id": str(run.id),
                "account_id": str(run.account_id),
                "filename": run.filename,
                "reason": str(exc),
            },
            actor_user_id=actor_user_id,
        )
        raise InvalidBankImportFileError(str(exc)) from exc

    row_count = len(rows)
    inserted_count = 0
    duplicate_count = 0
    error_count = 0

    # Pre-compute hashes and short-circuit duplicates before flush so the
    # session is never thrown into the "rolled-back-implicitly" state by an
    # IntegrityError mid-loop (a real risk on SQLite).
    #
    # We look up the set of already-stored hashes for this account up front,
    # then track in-batch duplicates in a Python set so two identical rows in
    # the same file also count toward duplicate_count without a DB round-trip.

    existing_hashes: set[str] = set()
    if row_count > 0:
        existing_hashes = set(
            (
                await session.execute(
                    select(BankTransaction.external_hash).where(
                        BankTransaction.account_id == account_id
                    )
                )
            )
            .scalars()
            .all()
        )

    seen_in_batch: set[str] = set()
    for row in rows:
        try:
            ext_hash = canonical_hash(
                account_id=account_id,
                occurred_on=row.occurred_on,
                amount=row.amount,
                description=row.description,
                fitid=row.fitid,
            )
        except Exception:
            error_count += 1
            continue

        if ext_hash in existing_hashes or ext_hash in seen_in_batch:
            duplicate_count += 1
            continue
        seen_in_batch.add(ext_hash)

        txn = BankTransaction(
            account_id=account_id,
            import_run_id=run.id,
            occurred_on=row.occurred_on,
            description=row.description,
            memo=row.memo,
            amount=row.amount,
            running_balance=row.running_balance,
            fitid=row.fitid,
            external_hash=ext_hash,
            state=BankTransactionState.UNMATCHED,
        )
        session.add(txn)
        inserted_count += 1

    try:
        await session.flush()
    except IntegrityError as exc:
        # Should not happen — the pre-check covers the only unique
        # constraint. If it does, surface clearly.
        raise InvalidBankImportFileError(f"unexpected dedup conflict: {exc}") from exc

    run.row_count = row_count
    run.inserted_count = inserted_count
    run.duplicate_count = duplicate_count
    run.error_count = error_count
    await session.flush()

    await _emit(
        session,
        event_type=banking_events.TYPE_IMPORT_RUN_COMPLETED,
        aggregate_type=banking_events.AGGREGATE_TYPE_BANK_IMPORT_RUN,
        aggregate_id=run.id,
        payload={
            "run_id": str(run.id),
            "account_id": str(run.account_id),
            "mapping_id": str(mapping.id) if mapping is not None else None,
            "filename": run.filename,
            "row_count": row_count,
            "inserted_count": inserted_count,
            "duplicate_count": duplicate_count,
            "error_count": error_count,
        },
        actor_user_id=actor_user_id,
    )
    return run


# ---------------------------------------------------------------------------
# Transaction list
# ---------------------------------------------------------------------------


async def list_transactions(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None = None,
    state: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> tuple[list[BankTransaction], str | None]:
    stmt = select(BankTransaction)
    if account_id is not None:
        stmt = stmt.where(BankTransaction.account_id == account_id)
    if state is not None:
        if state not in BankTransactionState._value2member_map_:
            raise BankImportsServiceError(f"invalid state {state!r}")
        stmt = stmt.where(BankTransaction.state == BankTransactionState(state))
    if date_from is not None:
        stmt = stmt.where(BankTransaction.occurred_on >= date_from)
    if date_to is not None:
        stmt = stmt.where(BankTransaction.occurred_on <= date_to)
    if search:
        pattern = f"%{search.lower()}%"
        from sqlalchemy import func

        stmt = stmt.where(
            or_(
                func.lower(BankTransaction.description).like(pattern),
                func.lower(BankTransaction.memo).like(pattern),
            )
        )

    if cursor is not None:
        try:
            cursor_ts_str, cursor_id_str = cursor.split("|", 1)
            cursor_ts = datetime.fromisoformat(cursor_ts_str)
            cursor_id = uuid.UUID(cursor_id_str)
        except Exception as exc:
            raise BankImportsServiceError(f"invalid cursor {cursor!r}") from exc
        stmt = stmt.where(
            or_(
                BankTransaction.imported_at < cursor_ts,
                and_(
                    BankTransaction.imported_at == cursor_ts,
                    BankTransaction.id < cursor_id,
                ),
            )
        )

    stmt = stmt.order_by(desc(BankTransaction.imported_at), desc(BankTransaction.id)).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = f"{last.imported_at.isoformat()}|{last.id}"
        rows = rows[:limit]
    return rows, next_cursor


__all__ = [
    "BankImportMappingNotFoundError",
    "BankImportRunNotFoundError",
    "BankImportsServiceError",
    "BankTransactionRow",
    "DuplicateBankImportMappingError",
    "InvalidBankImportFileError",
    "InvalidBankImportMappingError",
    "canonical_hash",
    "create_mapping",
    "deactivate_mapping",
    "get_mapping",
    "get_run",
    "import_file",
    "list_mappings",
    "list_transactions",
    "parse_csv",
    "parse_ofx",
    "update_mapping",
]
