"""Budgets service (Phase 4.5, #68).

A budget is the planned amount per ``(account_id, division_id, period_id)``
slot, where ``division_id`` is optional (NULL = catch-all per account/
period). The service owns both the upsert lifecycle and the variance
read model.

Sign convention
---------------
The variance read model uses the natural-balance convention per
``account.type``:

* asset / expense: actual = sum(debit) - sum(credit) (debit-natural)
* liability / equity / revenue: actual = sum(credit) - sum(debit)
  (credit-natural)

This way a revenue budget of $1000 paired with $800 of credit activity
yields ``actual_amount = 800`` (positive), and ``variance = actual -
budget = -200`` — i.e. under-realized.

Upsert + NULL-division
----------------------
On PG the migration declares ``UNIQUE (account_id, division_id, period_id)
NULLS NOT DISTINCT``, so an ON-CONFLICT upsert works for both NULL and
non-NULL division IDs. SQLite has no NULLS-NOT-DISTINCT support and
treats two NULL division_ids as distinct, so we look up the row
service-side first and switch between INSERT and UPDATE accordingly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting as accounting_events
from app.models.account import Account
from app.models.accounting_period import AccountingPeriod
from app.models.budget import Budget
from app.models.division import Division
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.schemas.events import EventCreate
from app.services import event_store

_QUANTUM = Decimal("0.000001")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BudgetsServiceError(Exception):
    """Base class. Routers default to 400."""


class BudgetNotFoundError(BudgetsServiceError):
    pass


class BudgetAmountInvalidError(BudgetsServiceError):
    pass


class BudgetAccountInvalidError(BudgetsServiceError):
    """Account is missing or archived."""


class BudgetDivisionInvalidError(BudgetsServiceError):
    """Division is missing or archived."""


class BudgetPeriodInvalidError(BudgetsServiceError):
    """Period is missing."""


# ---------------------------------------------------------------------------
# Result rows
# ---------------------------------------------------------------------------


@dataclass
class BudgetRow:
    id: uuid.UUID
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    division_id: uuid.UUID | None
    division_name: str | None
    division_code: str | None
    period_id: uuid.UUID
    amount: Decimal
    created_at: datetime
    updated_at: datetime


@dataclass
class BudgetVarianceRow:
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    division_id: uuid.UUID | None
    division_name: str | None
    budget_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    variance_pct: Decimal


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
            aggregate_type=accounting_events.AGGREGATE_TYPE_BUDGET,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM)


async def _load_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    row = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise BudgetAccountInvalidError(f"account {account_id} not found")
    if row.is_archived:
        raise BudgetAccountInvalidError(f"account {row.code!r} is archived")
    return row


async def _load_division(session: AsyncSession, division_id: uuid.UUID | None) -> Division | None:
    if division_id is None:
        return None
    row = (
        await session.execute(select(Division).where(Division.id == division_id))
    ).scalar_one_or_none()
    if row is None:
        raise BudgetDivisionInvalidError(f"division {division_id} not found")
    if row.is_archived:
        raise BudgetDivisionInvalidError(f"division {row.code!r} is archived")
    return row


async def _ensure_period(session: AsyncSession, period_id: uuid.UUID) -> AccountingPeriod:
    row = (
        await session.execute(select(AccountingPeriod).where(AccountingPeriod.id == period_id))
    ).scalar_one_or_none()
    if row is None:
        raise BudgetPeriodInvalidError(f"period {period_id} not found")
    return row


async def _find_existing(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    division_id: uuid.UUID | None,
    period_id: uuid.UUID,
) -> Budget | None:
    stmt = (
        select(Budget).where(Budget.account_id == account_id).where(Budget.period_id == period_id)
    )
    if division_id is None:
        stmt = stmt.where(Budget.division_id.is_(None))
    else:
        stmt = stmt.where(Budget.division_id == division_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class BudgetsService:
    """Stateless façade. Methods take an AsyncSession; caller owns commit."""

    @staticmethod
    async def set(
        account_id: uuid.UUID,
        division_id: uuid.UUID | None,
        period_id: uuid.UUID,
        amount: Decimal | str | int | float,
        *,
        session: AsyncSession,
        actor_user_id: uuid.UUID | None,
    ) -> Budget:
        """Upsert the budget row for ``(account, division, period)``.

        Emits ``accounting.BudgetSet`` with ``old_amount`` (NULL on
        create) and ``new_amount`` after the write.
        """
        amount_dec = _q(_to_decimal(amount))
        if amount_dec < 0:
            raise BudgetAmountInvalidError(f"amount must be >= 0, got {amount_dec}")

        await _load_account(session, account_id)
        await _load_division(session, division_id)
        await _ensure_period(session, period_id)

        existing = await _find_existing(
            session,
            account_id=account_id,
            division_id=division_id,
            period_id=period_id,
        )

        if existing is None:
            old_amount: Decimal | None = None
            row = Budget(
                id=uuid.uuid4(),
                account_id=account_id,
                division_id=division_id,
                period_id=period_id,
                amount=amount_dec,
            )
            session.add(row)
            await session.flush()
        else:
            old_amount = _q(_to_decimal(existing.amount))
            existing.amount = amount_dec
            await session.flush()
            row = existing

        await _emit(
            session,
            event_type=accounting_events.TYPE_BUDGET_SET,
            aggregate_id=row.id,
            payload={
                "account_id": str(account_id),
                "division_id": str(division_id) if division_id is not None else None,
                "period_id": str(period_id),
                "old_amount": (old_amount.to_eng_string() if old_amount is not None else None),
                "new_amount": amount_dec.to_eng_string(),
            },
            actor_user_id=actor_user_id,
        )
        return row

    @staticmethod
    async def unset(
        account_id: uuid.UUID,
        division_id: uuid.UUID | None,
        period_id: uuid.UUID,
        *,
        session: AsyncSession,
        actor_user_id: uuid.UUID | None,
    ) -> bool:
        """Delete the budget row for ``(account, division, period)`` if it
        exists. Returns ``True`` if a row was deleted, ``False`` otherwise.

        Emits ``accounting.BudgetUnset`` only on a real deletion.
        """
        existing = await _find_existing(
            session,
            account_id=account_id,
            division_id=division_id,
            period_id=period_id,
        )
        if existing is None:
            return False

        row_id = existing.id
        await session.delete(existing)
        await session.flush()

        await _emit(
            session,
            event_type=accounting_events.TYPE_BUDGET_UNSET,
            aggregate_id=row_id,
            payload={
                "account_id": str(account_id),
                "division_id": str(division_id) if division_id is not None else None,
                "period_id": str(period_id),
            },
            actor_user_id=actor_user_id,
        )
        return True

    @staticmethod
    async def list(
        *,
        session: AsyncSession,
        period_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
        division_id: uuid.UUID | None = None,
    ) -> list[BudgetRow]:
        stmt = (
            select(
                Budget,
                Account.code,
                Account.name,
                Account.type,
                Division.name,
                Division.code,
            )
            .join(Account, Account.id == Budget.account_id)
            .outerjoin(Division, Division.id == Budget.division_id)
        )
        if period_id is not None:
            stmt = stmt.where(Budget.period_id == period_id)
        if account_id is not None:
            stmt = stmt.where(Budget.account_id == account_id)
        if division_id is not None:
            stmt = stmt.where(Budget.division_id == division_id)

        stmt = stmt.order_by(Account.code, Division.code.nullsfirst())

        results: list[BudgetRow] = []
        for row, acct_code, acct_name, acct_type, div_name, div_code in (
            await session.execute(stmt)
        ).all():
            results.append(
                BudgetRow(
                    id=row.id,
                    account_id=row.account_id,
                    account_code=acct_code,
                    account_name=acct_name,
                    account_type=acct_type,
                    division_id=row.division_id,
                    division_name=div_name,
                    division_code=div_code,
                    period_id=row.period_id,
                    amount=_q(_to_decimal(row.amount)),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return results

    @staticmethod
    async def variance(
        period_id: uuid.UUID,
        *,
        session: AsyncSession,
        division_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[BudgetVarianceRow]:
        """Budget vs. actual for every budgeted slot in ``period_id``.

        Sums journal_line debits/credits per ``(account, division)`` for
        entries whose ``period_id`` matches. Applies the per-account-type
        sign convention (see module docstring) to compute ``actual_amount``
        and ``variance``.
        """
        await _ensure_period(session, period_id)

        budget_stmt = (
            select(
                Budget.account_id,
                Budget.division_id,
                Budget.amount,
                Account.code,
                Account.name,
                Account.type,
                Division.name,
            )
            .join(Account, Account.id == Budget.account_id)
            .outerjoin(Division, Division.id == Budget.division_id)
            .where(Budget.period_id == period_id)
        )
        if account_id is not None:
            budget_stmt = budget_stmt.where(Budget.account_id == account_id)
        if division_id is not None:
            budget_stmt = budget_stmt.where(Budget.division_id == division_id)

        budget_rows = list((await session.execute(budget_stmt)).all())

        # Sum journal-line activity per (account, division) for entries in
        # this period. We aggregate in one query and key by the pair.
        actuals_stmt = (
            select(
                JournalLine.account_id,
                JournalLine.division_id,
                func.coalesce(func.sum(JournalLine.debit), 0).label("debit_sum"),
                func.coalesce(func.sum(JournalLine.credit), 0).label("credit_sum"),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalEntry.period_id == period_id)
            .group_by(JournalLine.account_id, JournalLine.division_id)
        )
        actuals_map: dict[tuple[uuid.UUID, uuid.UUID | None], tuple[Decimal, Decimal]] = {}
        for acc_id, div_id, dsum, csum in (await session.execute(actuals_stmt)).all():
            actuals_map[(acc_id, div_id)] = (
                _to_decimal(dsum or 0),
                _to_decimal(csum or 0),
            )

        results: list[BudgetVarianceRow] = []
        for acc_id, div_id, amt, acct_code, acct_name, acct_type, div_name in budget_rows:
            budget_amount = _q(_to_decimal(amt))
            d_sum, c_sum = actuals_map.get((acc_id, div_id), (Decimal("0"), Decimal("0")))
            # liability / equity / revenue: credit-natural;
            # asset / expense: debit-natural.
            actual = d_sum - c_sum if acct_type in ("asset", "expense") else c_sum - d_sum
            actual = _q(actual)
            variance = _q(actual - budget_amount)
            if budget_amount == 0:
                variance_pct = Decimal("0.0000")
            else:
                variance_pct = (variance / budget_amount).quantize(Decimal("0.0001"))
            results.append(
                BudgetVarianceRow(
                    account_id=acc_id,
                    account_code=acct_code,
                    account_name=acct_name,
                    account_type=acct_type,
                    division_id=div_id,
                    division_name=div_name,
                    budget_amount=budget_amount,
                    actual_amount=actual,
                    variance=variance,
                    variance_pct=variance_pct,
                )
            )
        return results


# Silence unused-import warnings for symbols we keep around for type
# clarity in the docstring/sign-convention CASE expression in earlier
# drafts.
_ = (and_, case, text)


__all__ = [
    "BudgetAccountInvalidError",
    "BudgetAmountInvalidError",
    "BudgetDivisionInvalidError",
    "BudgetNotFoundError",
    "BudgetPeriodInvalidError",
    "BudgetRow",
    "BudgetVarianceRow",
    "BudgetsService",
    "BudgetsServiceError",
]
