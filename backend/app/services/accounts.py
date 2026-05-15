"""Chart-of-accounts service (Phase 4.1, #64).

The keystone of Phase 4 — every accounting mutation downstream
references an ``account`` row.

Structurally mirrors ``app.services.inventory_locations``: light CRUD
with an archive lifecycle, partial-unique guard on ``code``, and a typed
``accounting.Account*`` event appended via ``EventStore.append`` inside
the same transaction as the row write.

Hierarchy
---------
Each account has an optional ``parent_account_id`` (self-FK, ON DELETE
RESTRICT). Cycle detection on ``update`` mirrors the BOM pattern (#40):
walk the candidate parent's ancestor chain looking for the account
itself, with a depth limit of 50. Postgres uses ``WITH RECURSIVE``;
SQLite falls back to a Python loop. The asymmetry is documented inline.

Type consistency
----------------
A child's ``type`` must equal its parent's ``type``. This keeps roll-ups
sane — you can't accidentally hang an ``expense`` line under an
``asset`` subtree.

Archive
-------
Refuses to archive an account that has active descendants. A TODO
flags the future check (Phase 4.2): once journal-entry lines exist,
posted-line presence will also block archival.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, asc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting as accounting_events
from app.models.account import ACCOUNT_TYPE_VALUES, Account
from app.schemas.events import EventCreate
from app.services import event_store

DEFAULT_MAX_DEPTH: int = 50


class AccountsServiceError(Exception):
    """Base. Routers map to 400 unless overridden."""


class AccountNotFoundError(AccountsServiceError):
    pass


class DuplicateAccountCodeError(AccountsServiceError):
    pass


class InvalidCursorError(AccountsServiceError):
    pass


class InvalidAccountTypeError(AccountsServiceError):
    pass


class ParentNotFoundError(AccountsServiceError):
    pass


class AccountTypeMismatchError(AccountsServiceError):
    """Parent and child ``type`` disagree."""


class AccountCycleError(AccountsServiceError):
    """Reparenting would introduce a cycle."""


class AccountDepthLimitError(AccountsServiceError):
    pass


class ImmutableFieldError(AccountsServiceError):
    """A patch tried to change ``code`` or ``type``."""


class HasActiveDescendantsError(AccountsServiceError):
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
            aggregate_type=accounting_events.AGGREGATE_TYPE_ACCOUNT,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(code: str, account_id: uuid.UUID) -> str:
    raw = json.dumps({"c": code, "i": str(account_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return str(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


def _coerce_type(value: str) -> str:
    if value not in ACCOUNT_TYPE_VALUES:
        raise InvalidAccountTypeError(f"type must be one of {ACCOUNT_TYPE_VALUES}, got {value!r}")
    return value


async def _find_active_duplicate(
    session: AsyncSession,
    *,
    code: str,
    exclude_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    stmt = select(Account.id).where(Account.code == code).where(Account.is_archived.is_(False))
    if exclude_id is not None:
        stmt = stmt.where(Account.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load(session: AsyncSession, account_id: uuid.UUID) -> Account:
    row = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise AccountNotFoundError(str(account_id))
    return row


# ---------------------------------------------------------------------------
# Cycle / ancestor walk
# ---------------------------------------------------------------------------


async def _walks_to_ancestor(
    start_account_id: uuid.UUID,
    target_account_id: uuid.UUID,
    *,
    session: AsyncSession,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> bool:
    """Walk the parent chain of ``start_account_id`` and return True if
    ``target_account_id`` is encountered.

    Self-loop case (``start == target``) returns True immediately.

    Mirrors the BOM helper in :mod:`app.services.bom`: Postgres uses a
    recursive CTE; SQLite falls back to a Python loop. Both branches
    enforce ``max_depth`` and raise :class:`AccountDepthLimitError`
    on overflow.
    """
    if start_account_id == target_account_id:
        return True

    dialect = session.bind.dialect.name if session.bind is not None else ""

    if dialect == "postgresql":
        cte_sql = text(
            """
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_account_id, 1 AS depth
                FROM account
                WHERE id = :start
                UNION ALL
                SELECT a.id, a.parent_account_id, anc.depth + 1
                FROM account a
                JOIN ancestors anc ON a.id = anc.parent_account_id
                WHERE anc.depth < :max_depth
            )
            SELECT id, depth FROM ancestors
            """
        )
        rows = (
            await session.execute(
                cte_sql,
                {"start": start_account_id, "max_depth": max_depth},
            )
        ).all()
        for node_id, depth in rows:
            if depth > max_depth:
                raise AccountDepthLimitError(f"account parent chain exceeds {max_depth} levels")
            if node_id == target_account_id:
                return True
        return False

    # SQLite branch: Python-side loop. Mirrors the BOM helper structure.
    cursor: uuid.UUID | None = start_account_id
    depth = 0
    visited: set[uuid.UUID] = set()
    while cursor is not None:
        if cursor == target_account_id:
            return True
        if cursor in visited:
            # Defensive: a pre-existing cycle on disk would loop forever.
            return True
        visited.add(cursor)
        depth += 1
        if depth > max_depth:
            raise AccountDepthLimitError(f"account parent chain exceeds {max_depth} levels")
        parent_id = (
            await session.execute(select(Account.parent_account_id).where(Account.id == cursor))
        ).scalar_one_or_none()
        cursor = parent_id
    return False


async def _parent_chain(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[Account]:
    """Return the chain of ancestors from root down to direct parent.

    Does NOT include the account itself. Stops cleanly at the root.
    """
    target = await _load(session, account_id)
    chain: list[Account] = []
    cursor_id: uuid.UUID | None = target.parent_account_id
    depth = 0
    while cursor_id is not None:
        depth += 1
        if depth > max_depth:
            raise AccountDepthLimitError(f"account parent chain exceeds {max_depth} levels")
        parent = (
            await session.execute(select(Account).where(Account.id == cursor_id))
        ).scalar_one_or_none()
        if parent is None:
            break
        chain.append(parent)
        cursor_id = parent.parent_account_id
    chain.reverse()
    return chain


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    type: str,
    parent_account_id: uuid.UUID | None = None,
    description: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> Account:
    code_norm = code.strip()
    name_norm = name.strip()
    if not code_norm:
        raise AccountsServiceError("code is required")
    if not name_norm:
        raise AccountsServiceError("name is required")
    type_norm = _coerce_type(type)
    description_norm = description.strip() if description else None
    if description_norm == "":
        description_norm = None

    existing = await _find_active_duplicate(session, code=code_norm)
    if existing is not None:
        raise DuplicateAccountCodeError(
            f"active account with code {code_norm!r} already exists ({existing})"
        )

    if parent_account_id is not None:
        parent = (
            await session.execute(select(Account).where(Account.id == parent_account_id))
        ).scalar_one_or_none()
        if parent is None:
            raise ParentNotFoundError(str(parent_account_id))
        if parent.type != type_norm:
            raise AccountTypeMismatchError(
                f"parent account {parent.code!r} has type {parent.type!r}; "
                f"child must match (got {type_norm!r})"
            )

    account = Account(
        code=code_norm,
        name=name_norm,
        type=type_norm,
        parent_account_id=parent_account_id,
        description=description_norm,
        is_archived=False,
    )
    session.add(account)
    await session.flush()

    await _emit(
        session,
        event_type=accounting_events.TYPE_ACCOUNT_CREATED,
        aggregate_id=account.id,
        payload={
            "account_id": str(account.id),
            "code": account.code,
            "name": account.name,
            "type": account.type,
            "parent_account_id": (
                str(account.parent_account_id) if account.parent_account_id else None
            ),
        },
        actor_user_id=actor_user_id,
    )
    return account


async def get(session: AsyncSession, account_id: uuid.UUID) -> Account:
    return await _load(session, account_id)


@dataclass
class AccountWithChain:
    account: Account
    parent_chain: list[Account] = field(default_factory=list)


async def get_with_chain(session: AsyncSession, account_id: uuid.UUID) -> AccountWithChain:
    account = await _load(session, account_id)
    chain = await _parent_chain(session, account_id)
    return AccountWithChain(account=account, parent_chain=chain)


# Editable via PATCH. ``code`` and ``type`` are NOT here on purpose.
_EDITABLE_FIELDS = frozenset({"name", "description", "parent_account_id"})
_IMMUTABLE_FIELDS = frozenset({"code", "type"})


async def update(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Account:
    forbidden = _IMMUTABLE_FIELDS & set(patch.keys())
    if forbidden:
        raise ImmutableFieldError(f"these fields are not editable: {sorted(forbidden)}")

    target = await _load(session, account_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field_name, new_value in patch.items():
        if field_name not in _EDITABLE_FIELDS:
            # Schema should already prevent it; defensive skip.
            continue
        if field_name == "name":
            if not isinstance(new_value, str) or not new_value.strip():
                raise AccountsServiceError("name must not be empty")
            new_value = new_value.strip()
        elif field_name == "description":
            if isinstance(new_value, str):
                stripped = new_value.strip()
                new_value = None if stripped == "" else stripped
        elif field_name == "parent_account_id":
            # Allowed None (detach) or a UUID.
            if new_value is not None and not isinstance(new_value, uuid.UUID):
                try:
                    new_value = uuid.UUID(str(new_value))
                except (TypeError, ValueError) as exc:
                    raise AccountsServiceError(f"invalid parent_account_id: {exc}") from exc

        current = getattr(target, field_name)
        if current == new_value:
            continue

        if field_name == "parent_account_id" and new_value is not None:
            # Cycle + type-consistency checks.
            if new_value == target.id:
                raise AccountCycleError(f"account {target.id} cannot be its own parent")
            new_parent = (
                await session.execute(select(Account).where(Account.id == new_value))
            ).scalar_one_or_none()
            if new_parent is None:
                raise ParentNotFoundError(str(new_value))
            if new_parent.type != target.type:
                raise AccountTypeMismatchError(
                    f"parent account {new_parent.code!r} has type "
                    f"{new_parent.type!r}; child must match (got {target.type!r})"
                )
            # Walk the new parent's chain; if target appears there, cycle.
            hits = await _walks_to_ancestor(new_value, target.id, session=session)
            if hits:
                raise AccountCycleError(
                    f"setting parent of {target.id} to {new_value} would " "create a cycle"
                )

        before[field_name] = _serialize_field(current)
        after[field_name] = _serialize_field(new_value)
        setattr(target, field_name, new_value)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=accounting_events.TYPE_ACCOUNT_UPDATED,
        aggregate_id=target.id,
        payload={
            "account_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


def _serialize_field(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def archive(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Account:
    target = await _load(session, account_id)
    if target.is_archived:
        return target

    # Refuse if any active descendants exist.
    active_child = (
        await session.execute(
            select(Account.id)
            .where(Account.parent_account_id == target.id)
            .where(Account.is_archived.is_(False))
            .limit(1)
        )
    ).scalar_one_or_none()
    if active_child is not None:
        raise HasActiveDescendantsError(
            f"account {target.code!r} has active descendants; archive them first"
        )

    # TODO(#4.2): Once journal entries exist, also refuse to archive
    # accounts with posted lines.

    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_ACCOUNT_ARCHIVED,
        aggregate_id=target.id,
        payload={"account_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Account:
    target = await _load(session, account_id)
    if not target.is_archived:
        return target

    existing = await _find_active_duplicate(session, code=target.code, exclude_id=target.id)
    if existing is not None:
        raise DuplicateAccountCodeError(
            f"cannot unarchive: another active account uses code {target.code!r}"
        )

    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_ACCOUNT_UNARCHIVED,
        aggregate_id=target.id,
        payload={"account_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class AccountPage:
    items: list[Account]
    next_cursor: str | None


async def list_accounts(
    session: AsyncSession,
    *,
    search: str | None = None,
    type: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> AccountPage:
    stmt = select(Account)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Account.code).like(pattern),
                func.lower(Account.name).like(pattern),
            )
        )
    if type is not None:
        stmt = stmt.where(Account.type == _coerce_type(type))
    if is_archived is not None:
        stmt = stmt.where(Account.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_code, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Account.code > anchor_code,
                and_(Account.code == anchor_code, Account.id > anchor_id),
            )
        )
    stmt = stmt.order_by(asc(Account.code), asc(Account.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].code, rows[-1].id) if (rows and has_more) else None
    return AccountPage(items=rows, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


@dataclass
class AccountTreeNode:
    account: Account
    children: list[AccountTreeNode] = field(default_factory=list)


async def tree(
    session: AsyncSession,
    *,
    include_archived: bool = False,
) -> list[AccountTreeNode]:
    stmt = select(Account)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    stmt = stmt.order_by(asc(Account.code), asc(Account.id))
    rows = list((await session.execute(stmt)).scalars().all())

    nodes: dict[uuid.UUID, AccountTreeNode] = {row.id: AccountTreeNode(account=row) for row in rows}
    roots: list[AccountTreeNode] = []
    for row in rows:
        node = nodes[row.id]
        parent_id = row.parent_account_id
        if parent_id is not None and parent_id in nodes:
            nodes[parent_id].children.append(node)
        else:
            # Top-level: explicit NULL parent, or parent filtered out
            # (e.g. archived parent while include_archived=False).
            roots.append(node)
    return roots


__all__ = [
    "AccountCycleError",
    "AccountDepthLimitError",
    "AccountNotFoundError",
    "AccountPage",
    "AccountTreeNode",
    "AccountTypeMismatchError",
    "AccountWithChain",
    "AccountsServiceError",
    "DuplicateAccountCodeError",
    "HasActiveDescendantsError",
    "ImmutableFieldError",
    "InvalidAccountTypeError",
    "InvalidCursorError",
    "ParentNotFoundError",
    "archive",
    "create",
    "get",
    "get_with_chain",
    "list_accounts",
    "tree",
    "unarchive",
    "update",
    "_walks_to_ancestor",
]
