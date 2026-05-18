"""Bank match-rule CRUD service (Phase 8.10, #137).

Operator-defined matchers used by ``bank_auto_matcher.run_once`` to
classify ``bank_transaction`` rows. The matchers themselves are pure
helpers compiled at scan time.

Priority semantics
------------------
* ``priority`` is a small integer; **lower runs first**.
* At equal ``priority``, **per-account rules win over global** rules.
* Within those two classes the order is deterministic (by ``id``) so
  test assertions are stable.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import banking as banking_events
from app.models.account import Account
from app.models.bank_match_rule import (
    BankMatchAction,
    BankMatchField,
    BankMatchRule,
    BankMatchRuleKind,
)
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BankMatchRulesServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class BankMatchRuleNotFoundError(BankMatchRulesServiceError):
    """Mapped to 404."""


class InvalidBankMatchRuleError(BankMatchRulesServiceError):
    """Validation failure."""


# ---------------------------------------------------------------------------
# Compiled matcher helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledMatcher:
    """A compiled, callable matcher tied back to its rule.

    ``matches(field_value, amount)`` returns True iff the rule fires for
    the supplied transaction values. The compile step pulls out the
    pattern + bounds once so the per-transaction call is cheap.
    """

    rule: BankMatchRule
    _predicate: Callable[[str], bool]
    _min_amount: Decimal | None
    _max_amount: Decimal | None
    field: BankMatchField

    def matches(self, *, description: str, memo: str | None, amount: Decimal) -> bool:
        if self.field == BankMatchField.MEMO:
            candidate = (memo or "").strip()
        else:
            candidate = (description or "").strip()
        if not self._predicate(candidate):
            return False
        if self._min_amount is not None and amount < self._min_amount:
            return False
        return not (self._max_amount is not None and amount > self._max_amount)


def _build_predicate(kind: BankMatchRuleKind, value: str) -> Callable[[str], bool]:
    if kind == BankMatchRuleKind.REGEX:
        try:
            pattern = re.compile(value)
        except re.error as exc:
            raise InvalidBankMatchRuleError(f"invalid regex {value!r}: {exc}") from exc
        return lambda candidate: pattern.search(candidate) is not None
    needle = value.casefold()
    if kind == BankMatchRuleKind.CONTAINS:
        return lambda candidate: needle in candidate.casefold()
    if kind == BankMatchRuleKind.STARTS_WITH:
        return lambda candidate: candidate.casefold().startswith(needle)
    if kind == BankMatchRuleKind.EQUALS:
        return lambda candidate: candidate.casefold() == needle
    raise InvalidBankMatchRuleError(f"unknown match_kind {kind!r}")


def compile_matchers(rules: list[BankMatchRule]) -> list[CompiledMatcher]:
    """Pure helper: compile a list of rules into reusable matchers.

    Already-ordered input is preserved (the worker controls ordering); a
    bad regex inside one rule raises :class:`InvalidBankMatchRuleError`
    immediately rather than silently skipping it.
    """
    out: list[CompiledMatcher] = []
    for rule in rules:
        predicate = _build_predicate(rule.match_kind, rule.match_value)
        out.append(
            CompiledMatcher(
                rule=rule,
                _predicate=predicate,
                _min_amount=rule.min_amount,
                _max_amount=rule.max_amount,
                field=rule.match_field,
            )
        )
    return out


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
            aggregate_type=banking_events.AGGREGATE_TYPE_BANK_MATCH_RULE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def _check_account_exists(session: AsyncSession, account_id: uuid.UUID) -> None:
    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidBankMatchRuleError(f"account {account_id} does not exist")


def _validate_match_value(match_kind: BankMatchRuleKind, match_value: str) -> None:
    if not match_value or not match_value.strip():
        raise InvalidBankMatchRuleError("match_value must be a non-empty string")
    if match_kind == BankMatchRuleKind.REGEX:
        try:
            re.compile(match_value)
        except re.error as exc:
            raise InvalidBankMatchRuleError(f"invalid regex {match_value!r}: {exc}") from exc


def _validate_action(
    action_kind: BankMatchAction,
    debit_account_id: uuid.UUID | None,
    credit_account_id: uuid.UUID | None,
) -> None:
    if action_kind == BankMatchAction.POST_TO_ACCOUNT and (
        debit_account_id is None or credit_account_id is None
    ):
        raise InvalidBankMatchRuleError(
            "action_kind=post_to_account requires both debit_account_id and " "credit_account_id"
        )


def _coerce_enum(value: Any, enum_cls: type[Any], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str) and value in enum_cls._value2member_map_:
        return enum_cls(value)
    raise InvalidBankMatchRuleError(f"invalid {field_name}: {value!r}")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    *,
    session: AsyncSession,
    account_id: uuid.UUID | None,
    priority: int,
    match_kind: str,
    match_field: str,
    match_value: str,
    action_kind: str,
    debit_account_id: uuid.UUID | None = None,
    credit_account_id: uuid.UUID | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    description_template: str | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> BankMatchRule:
    kind = _coerce_enum(match_kind, BankMatchRuleKind, "match_kind")
    field = _coerce_enum(match_field, BankMatchField, "match_field")
    action = _coerce_enum(action_kind, BankMatchAction, "action_kind")
    _validate_match_value(kind, match_value)
    _validate_action(action, debit_account_id, credit_account_id)
    if account_id is not None:
        await _check_account_exists(session, account_id)
    if debit_account_id is not None:
        await _check_account_exists(session, debit_account_id)
    if credit_account_id is not None:
        await _check_account_exists(session, credit_account_id)
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise InvalidBankMatchRuleError("min_amount must be <= max_amount")

    notes_clean = notes.strip() if isinstance(notes, str) and notes.strip() else None
    template_clean = (
        description_template.strip()
        if isinstance(description_template, str) and description_template.strip()
        else None
    )

    row = BankMatchRule(
        account_id=account_id,
        priority=priority,
        match_kind=kind,
        match_field=field,
        match_value=match_value,
        min_amount=min_amount,
        max_amount=max_amount,
        action_kind=action,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        description_template=template_clean,
        is_active=True,
        notes=notes_clean,
        created_by_user_id=actor_user_id,
    )
    session.add(row)
    await session.flush()

    await _emit(
        session,
        event_type=banking_events.TYPE_MATCH_RULE_CREATED,
        aggregate_id=row.id,
        payload={
            "rule_id": str(row.id),
            "account_id": str(row.account_id) if row.account_id else None,
            "priority": row.priority,
            "match_kind": row.match_kind.value,
            "match_field": row.match_field.value,
            "match_value": row.match_value,
            "action_kind": row.action_kind.value,
            "debit_account_id": str(row.debit_account_id) if row.debit_account_id else None,
            "credit_account_id": str(row.credit_account_id) if row.credit_account_id else None,
            "min_amount": str(row.min_amount) if row.min_amount is not None else None,
            "max_amount": str(row.max_amount) if row.max_amount is not None else None,
            "description_template": row.description_template,
            "notes": row.notes,
        },
        actor_user_id=actor_user_id,
    )
    return row


_EDITABLE = (
    "priority",
    "match_kind",
    "match_field",
    "match_value",
    "action_kind",
    "debit_account_id",
    "credit_account_id",
    "min_amount",
    "max_amount",
    "description_template",
    "notes",
    "is_active",
)


def _serialize_for_event(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, BankMatchAction | BankMatchField | BankMatchRuleKind):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


async def get(session: AsyncSession, rule_id: uuid.UUID) -> BankMatchRule:
    row = (
        await session.execute(select(BankMatchRule).where(BankMatchRule.id == rule_id))
    ).scalar_one_or_none()
    if row is None:
        raise BankMatchRuleNotFoundError(str(rule_id))
    return row


async def update(
    *,
    session: AsyncSession,
    rule_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> BankMatchRule:
    target = await get(session, rule_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    new_action = target.action_kind
    new_debit = target.debit_account_id
    new_credit = target.credit_account_id

    for field_name in _EDITABLE:
        if field_name not in patch:
            continue
        new_value = patch[field_name]
        if field_name == "match_kind" and new_value is not None:
            new_value = _coerce_enum(new_value, BankMatchRuleKind, "match_kind")
        elif field_name == "match_field" and new_value is not None:
            new_value = _coerce_enum(new_value, BankMatchField, "match_field")
        elif field_name == "action_kind" and new_value is not None:
            new_value = _coerce_enum(new_value, BankMatchAction, "action_kind")
            new_action = new_value
        elif field_name == "debit_account_id":
            new_debit = new_value
            if new_value is not None:
                await _check_account_exists(session, new_value)
        elif field_name == "credit_account_id":
            new_credit = new_value
            if new_value is not None:
                await _check_account_exists(session, new_value)
        elif field_name == "match_value" and new_value is not None:
            if not isinstance(new_value, str) or not new_value.strip():
                raise InvalidBankMatchRuleError("match_value must not be empty")
        elif field_name in ("notes", "description_template") and isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = stripped or None

        current = getattr(target, field_name)
        if current == new_value:
            continue
        before[field_name] = _serialize_for_event(current)
        after[field_name] = _serialize_for_event(new_value)
        setattr(target, field_name, new_value)

    # Re-validate regex when match_kind or match_value changed.
    _validate_match_value(target.match_kind, target.match_value)
    _validate_action(new_action, new_debit, new_credit)
    if (
        target.min_amount is not None
        and target.max_amount is not None
        and target.min_amount > target.max_amount
    ):
        raise InvalidBankMatchRuleError("min_amount must be <= max_amount")

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=banking_events.TYPE_MATCH_RULE_UPDATED,
        aggregate_id=target.id,
        payload={
            "rule_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def deactivate(
    *,
    session: AsyncSession,
    rule_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> BankMatchRule:
    target = await get(session, rule_id)
    if not target.is_active:
        return target
    target.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=banking_events.TYPE_MATCH_RULE_DEACTIVATED,
        aggregate_id=target.id,
        payload={"rule_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def list_rules(
    *,
    session: AsyncSession,
    account_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    only_account_id: bool = False,
    limit: int = 200,
) -> list[BankMatchRule]:
    """List rules. Default ordering matches the worker's evaluation order:

    * by ``priority`` ascending
    * then per-account rules (NOT NULL ``account_id``) before global rules
    * then by ``id`` to be deterministic

    Filters:
    * ``account_id`` — when set with ``only_account_id=False`` (default),
      returns rules matching that account **and** global rules. With
      ``only_account_id=True``, only rules for that exact account_id are
      returned (matching the API contract for the per-account list view).
    * ``include_inactive`` — drop the is_active=True filter.
    """
    stmt = select(BankMatchRule)
    if not include_inactive:
        stmt = stmt.where(BankMatchRule.is_active.is_(True))
    if account_id is not None:
        if only_account_id:
            stmt = stmt.where(BankMatchRule.account_id == account_id)
        else:
            stmt = stmt.where(
                (BankMatchRule.account_id == account_id) | (BankMatchRule.account_id.is_(None))
            )
    stmt = stmt.order_by(
        asc(BankMatchRule.priority),
        # NULLs (global) sort last via this ordering trick:
        asc(BankMatchRule.account_id.is_(None)),
        asc(BankMatchRule.id),
    ).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "BankMatchRuleNotFoundError",
    "BankMatchRulesServiceError",
    "CompiledMatcher",
    "InvalidBankMatchRuleError",
    "compile_matchers",
    "create",
    "deactivate",
    "get",
    "list_rules",
    "update",
]
