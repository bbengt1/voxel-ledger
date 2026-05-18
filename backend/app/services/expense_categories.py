"""Expense categories service (Phase 8.6, #133).

Light CRUD over the ``expense_category`` aggregate. Each mutation
appends a typed ``ap.ExpenseCategory*`` event via ``EventStore.append``
inside the same transaction as the row write.

Validation rules
----------------
* ``code`` non-empty and unique (DB unique constraint backs the service
  check; we catch IntegrityError and surface as DuplicateError).
* ``name`` non-empty.
* ``default_expense_account_id`` must reference an existing
  ``account`` row with ``type='expense'``.
* ``parent_id`` (if set) must reference an active expense category
  whose ``parent_id IS NULL`` (one-level hierarchy only). On update the
  parent cannot be the row itself (cycle prevention).
* ``delete`` is only allowed when no ``bill_item`` or
  ``recurring_bill_template_item`` row references the category — else
  400 with "category in use; archive instead".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import asc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ap as ap_events
from app.models.account import Account
from app.models.bill import BillItem
from app.models.expense_category import ExpenseCategory
from app.models.recurring_bill import RecurringBillTemplateItem
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExpenseCategoriesServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class ExpenseCategoryNotFoundError(ExpenseCategoriesServiceError):
    """Mapped to 404."""


class DuplicateExpenseCategoryError(ExpenseCategoriesServiceError):
    """``code`` collides with another row."""


class InvalidExpenseCategoryError(ExpenseCategoriesServiceError):
    """Field-level validation failed (bad account, bad parent, etc.)."""


class ExpenseCategoryInUseError(ExpenseCategoriesServiceError):
    """Delete blocked because bill or recurring template items reference it."""


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
            aggregate_type=ap_events.AGGREGATE_TYPE_EXPENSE_CATEGORY,
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


async def _validate_expense_account(session: AsyncSession, account_id: uuid.UUID) -> None:
    row = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise InvalidExpenseCategoryError(f"default_expense_account_id {account_id} does not exist")
    if str(row.type) != "expense":
        raise InvalidExpenseCategoryError(
            f"default_expense_account_id {account_id} must be type=expense (got {row.type!r})"
        )


async def _validate_parent(
    session: AsyncSession,
    parent_id: uuid.UUID,
    *,
    self_id: uuid.UUID | None = None,
) -> None:
    if self_id is not None and parent_id == self_id:
        raise InvalidExpenseCategoryError("parent_id may not reference self")
    parent = (
        await session.execute(select(ExpenseCategory).where(ExpenseCategory.id == parent_id))
    ).scalar_one_or_none()
    if parent is None:
        raise InvalidExpenseCategoryError(f"parent_id {parent_id} does not exist")
    if not parent.is_active:
        raise InvalidExpenseCategoryError(f"parent_id {parent_id} is archived")
    if parent.parent_id is not None:
        raise InvalidExpenseCategoryError("expense categories support only one level of nesting")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, category_id: uuid.UUID) -> ExpenseCategory:
    row = (
        await session.execute(select(ExpenseCategory).where(ExpenseCategory.id == category_id))
    ).scalar_one_or_none()
    if row is None:
        raise ExpenseCategoryNotFoundError(str(category_id))
    return row


async def create(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    default_expense_account_id: uuid.UUID,
    parent_id: uuid.UUID | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> ExpenseCategory:
    code = code.strip()
    name = name.strip()
    if not code:
        raise ExpenseCategoriesServiceError("code is required")
    if not name:
        raise ExpenseCategoriesServiceError("name is required")

    await _validate_expense_account(session, default_expense_account_id)
    if parent_id is not None:
        await _validate_parent(session, parent_id)

    notes_clean = notes.strip() if isinstance(notes, str) else None
    if notes_clean == "":
        notes_clean = None

    category = ExpenseCategory(
        code=code,
        name=name,
        default_expense_account_id=default_expense_account_id,
        parent_id=parent_id,
        is_active=True,
        notes=notes_clean,
    )
    session.add(category)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateExpenseCategoryError(
            f"expense category with code={code!r} already exists"
        ) from exc

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CATEGORY_CREATED,
        aggregate_id=category.id,
        payload={
            "expense_category_id": str(category.id),
            "code": category.code,
            "name": category.name,
            "default_expense_account_id": str(category.default_expense_account_id),
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "is_active": category.is_active,
            "notes": category.notes,
        },
        actor_user_id=actor_user_id,
    )
    return category


_EDITABLE_FIELDS = (
    "code",
    "name",
    "default_expense_account_id",
    "parent_id",
    "is_active",
    "notes",
)


def _serialize(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def update(
    session: AsyncSession,
    *,
    category_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> ExpenseCategory:
    target = await get(session, category_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("code", "name") and new_value is not None:
            if not isinstance(new_value, str) or not new_value.strip():
                raise ExpenseCategoriesServiceError(f"{field} must not be empty")
            new_value = new_value.strip()
        elif field == "notes":
            if isinstance(new_value, str):
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

    if "default_expense_account_id" in before:
        await _validate_expense_account(session, target.default_expense_account_id)
    if "parent_id" in before and target.parent_id is not None:
        await _validate_parent(session, target.parent_id, self_id=target.id)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateExpenseCategoryError(
            f"another expense category uses code={target.code!r}"
        ) from exc

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CATEGORY_UPDATED,
        aggregate_id=target.id,
        payload={
            "expense_category_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    category_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> ExpenseCategory:
    target = await get(session, category_id)
    if not target.is_active:
        return target
    target.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CATEGORY_ARCHIVED,
        aggregate_id=target.id,
        payload={
            "expense_category_id": str(target.id),
            "code": target.code,
            "name": target.name,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def delete(
    session: AsyncSession,
    *,
    category_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    target = await get(session, category_id)

    bill_ref = (
        await session.execute(
            select(BillItem.id).where(BillItem.expense_category_id == target.id).limit(1)
        )
    ).scalar_one_or_none()
    if bill_ref is not None:
        raise ExpenseCategoryInUseError("category in use; archive instead")

    template_ref = (
        await session.execute(
            select(RecurringBillTemplateItem.id)
            .where(RecurringBillTemplateItem.expense_category_id == target.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if template_ref is not None:
        raise ExpenseCategoryInUseError("category in use; archive instead")

    await session.delete(target)
    await session.flush()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def list_categories(
    session: AsyncSession,
    *,
    active: bool | None = None,
    search: str | None = None,
    parent_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[ExpenseCategory]:
    stmt = select(ExpenseCategory)
    if active is not None:
        stmt = stmt.where(ExpenseCategory.is_active.is_(active))
    if parent_id is not None:
        stmt = stmt.where(ExpenseCategory.parent_id == parent_id)
    if search:
        pattern = f"%{search.lower()}%"
        from sqlalchemy import func

        stmt = stmt.where(
            or_(
                func.lower(ExpenseCategory.code).like(pattern),
                func.lower(ExpenseCategory.name).like(pattern),
            )
        )
    stmt = stmt.order_by(asc(ExpenseCategory.code)).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Lookup helper for bill issue chain
# ---------------------------------------------------------------------------


async def get_default_account_for_category(
    session: AsyncSession,
    category_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Return the category's ``default_expense_account_id`` or ``None``.

    Used by ``bills.issue`` as the second link in the expense-account
    resolution chain (line override -> category default -> vendor
    default -> setting fallback).
    """
    if category_id is None:
        return None
    row = (
        await session.execute(
            select(ExpenseCategory.default_expense_account_id).where(
                ExpenseCategory.id == category_id
            )
        )
    ).scalar_one_or_none()
    return row


__all__ = [
    "DuplicateExpenseCategoryError",
    "ExpenseCategoriesServiceError",
    "ExpenseCategoryInUseError",
    "ExpenseCategoryNotFoundError",
    "InvalidExpenseCategoryError",
    "archive",
    "create",
    "delete",
    "get",
    "get_default_account_for_category",
    "list_categories",
    "update",
]
