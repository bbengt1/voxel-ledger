"""Late-fee policy CRUD service (Phase 7.6, #114).

A late-fee policy is a rule the daily late-fee worker uses to compute
a debit-note amount against an overdue invoice. Rows can be scoped to
a customer (``customer_id IS NOT NULL``) or global
(``customer_id IS NULL``). The worker prefers customer-specific over
global at evaluation time.

All write paths emit ``ar.LateFeePolicy*`` events in the same TX so
the audit log captures them. The caller owns the transaction —
the service never commits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ar as ar_events
from app.models.customer import Customer
from app.models.late_fee_policy import LateFeeKind, LateFeePolicy
from app.schemas.events import EventCreate
from app.services import event_store


class LateFeePolicyServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class LateFeePolicyNotFoundError(LateFeePolicyServiceError):
    """Mapped to 404."""


class InvalidLateFeePolicyError(LateFeePolicyServiceError):
    """Validation failed (bad amount, bad customer ref, etc.)."""


def _coerce_kind(value: str | LateFeeKind) -> LateFeeKind:
    if isinstance(value, LateFeeKind):
        return value
    try:
        return LateFeeKind(value)
    except ValueError as exc:
        raise InvalidLateFeePolicyError(f"invalid late_fee_kind: {value!r}") from exc


def _validate_amount(kind: LateFeeKind, amount: Decimal | str | int | float) -> Decimal:
    try:
        d = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except (ValueError, ArithmeticError) as exc:
        raise InvalidLateFeePolicyError(f"invalid amount: {amount!r}") from exc
    if d <= 0:
        raise InvalidLateFeePolicyError("amount must be > 0")
    if kind in (LateFeeKind.PERCENT_OF_OUTSTANDING, LateFeeKind.COMPOUND_PERCENT) and d >= 1:
        # 1.0 = 100%. Anything bigger is almost surely a bad value.
        raise InvalidLateFeePolicyError("percent amount must be < 1 (e.g. 0.015 = 1.5%)")
    return d


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
            aggregate_type=ar_events.AGGREGATE_TYPE_LATE_FEE_POLICY,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _load(session: AsyncSession, policy_id: uuid.UUID) -> LateFeePolicy:
    stmt = select(LateFeePolicy).where(LateFeePolicy.id == policy_id)
    policy = (await session.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise LateFeePolicyNotFoundError(str(policy_id))
    return policy


async def create(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None,
    kind: str | LateFeeKind,
    amount: Decimal | str | int | float,
    grace_period_days: int = 0,
    apply_after_days: int = 30,
    compound_interval_days: int = 30,
    is_active: bool = True,
    actor_user_id: uuid.UUID | None,
) -> LateFeePolicy:
    kind_e = _coerce_kind(kind)
    amount_d = _validate_amount(kind_e, amount)

    if grace_period_days < 0:
        raise InvalidLateFeePolicyError("grace_period_days must be >= 0")
    if apply_after_days < 0:
        raise InvalidLateFeePolicyError("apply_after_days must be >= 0")
    if compound_interval_days <= 0:
        raise InvalidLateFeePolicyError("compound_interval_days must be > 0")

    if customer_id is not None:
        exists = (
            await session.execute(select(Customer.id).where(Customer.id == customer_id))
        ).scalar_one_or_none()
        if exists is None:
            raise InvalidLateFeePolicyError(f"customer {customer_id} not found")

    policy = LateFeePolicy(
        customer_id=customer_id,
        kind=kind_e,
        amount=amount_d,
        grace_period_days=grace_period_days,
        apply_after_days=apply_after_days,
        compound_interval_days=compound_interval_days,
        is_active=is_active,
    )
    session.add(policy)
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_LATE_FEE_POLICY_CREATED,
        aggregate_id=policy.id,
        payload={
            "policy_id": str(policy.id),
            "customer_id": str(customer_id) if customer_id else None,
            "kind": kind_e.value,
            "amount": str(amount_d),
            "grace_period_days": grace_period_days,
            "apply_after_days": apply_after_days,
            "compound_interval_days": compound_interval_days,
            "is_active": is_active,
        },
        actor_user_id=actor_user_id,
    )
    return policy


async def update(
    session: AsyncSession,
    *,
    policy_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    **fields: Any,
) -> LateFeePolicy:
    policy = await _load(session, policy_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    if "kind" in fields and fields["kind"] is not None:
        new_kind = _coerce_kind(fields["kind"])
        if new_kind != policy.kind:
            before["kind"] = policy.kind.value
            after["kind"] = new_kind.value
            policy.kind = new_kind
    if "amount" in fields and fields["amount"] is not None:
        new_amount = _validate_amount(policy.kind, fields["amount"])
        if new_amount != policy.amount:
            before["amount"] = str(policy.amount)
            after["amount"] = str(new_amount)
            policy.amount = new_amount
    for int_field in ("grace_period_days", "apply_after_days", "compound_interval_days"):
        if int_field in fields and fields[int_field] is not None:
            new_val = int(fields[int_field])
            if int_field == "compound_interval_days" and new_val <= 0:
                raise InvalidLateFeePolicyError("compound_interval_days must be > 0")
            if int_field != "compound_interval_days" and new_val < 0:
                raise InvalidLateFeePolicyError(f"{int_field} must be >= 0")
            current = getattr(policy, int_field)
            if current != new_val:
                before[int_field] = current
                after[int_field] = new_val
                setattr(policy, int_field, new_val)
    if "customer_id" in fields:
        new_cust = fields["customer_id"]
        if new_cust is not None and isinstance(new_cust, str):
            new_cust = uuid.UUID(new_cust)
        if new_cust != policy.customer_id:
            if new_cust is not None:
                exists = (
                    await session.execute(select(Customer.id).where(Customer.id == new_cust))
                ).scalar_one_or_none()
                if exists is None:
                    raise InvalidLateFeePolicyError(f"customer {new_cust} not found")
            before["customer_id"] = str(policy.customer_id) if policy.customer_id else None
            after["customer_id"] = str(new_cust) if new_cust else None
            policy.customer_id = new_cust
    if "is_active" in fields and fields["is_active"] is not None:
        new_active = bool(fields["is_active"])
        if new_active != policy.is_active:
            before["is_active"] = policy.is_active
            after["is_active"] = new_active
            policy.is_active = new_active

    await session.flush()

    if before or after:
        await _emit(
            session,
            event_type=ar_events.TYPE_LATE_FEE_POLICY_UPDATED,
            aggregate_id=policy.id,
            payload={
                "policy_id": str(policy.id),
                "before": before,
                "after": after,
            },
            actor_user_id=actor_user_id,
        )
    return policy


async def deactivate(
    session: AsyncSession,
    *,
    policy_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> LateFeePolicy:
    policy = await _load(session, policy_id)
    if not policy.is_active:
        return policy
    policy.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_LATE_FEE_POLICY_DEACTIVATED,
        aggregate_id=policy.id,
        payload={"policy_id": str(policy.id)},
        actor_user_id=actor_user_id,
    )
    return policy


async def get(session: AsyncSession, policy_id: uuid.UUID) -> LateFeePolicy:
    return await _load(session, policy_id)


async def list_policies(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
) -> list[LateFeePolicy]:
    stmt = select(LateFeePolicy).order_by(LateFeePolicy.created_at.desc())
    if not include_inactive:
        stmt = stmt.where(LateFeePolicy.is_active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def resolve_for_customer(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
) -> LateFeePolicy | None:
    """Return the most-specific active policy for a customer, or ``None``.

    Customer-specific policy beats global; among ties (shouldn't
    happen — one per customer is enforced by convention) we pick the
    newest by ``created_at``.
    """
    stmt = (
        select(LateFeePolicy)
        .where(LateFeePolicy.is_active.is_(True))
        .where((LateFeePolicy.customer_id == customer_id) | (LateFeePolicy.customer_id.is_(None)))
        .order_by(
            # NULL last (so a customer-specific row wins). PG and SQLite
            # both order NULLs last by default with DESC on a non-null
            # field — but here ``customer_id`` itself is the discriminant,
            # so order by an expression that puts non-null first.
            LateFeePolicy.customer_id.is_(None),
            LateFeePolicy.created_at.desc(),
        )
    )
    return (await session.execute(stmt)).scalars().first()
