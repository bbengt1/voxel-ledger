"""Expense claims service (Phase 8.7, #134).

Owns the ``expense_claim`` aggregate + its ``expense_claim_line`` rows.
Claim numbers are allocated via the race-safe reference allocator with
prefix ``EXP``.

State machine
-------------

    draft     -> submitted    (submitter; threshold gating may attach
                               an ApprovalRequest)
    submitted -> approved     (owner/bookkeeper; posts JE atomically)
    submitted -> rejected     (owner/bookkeeper; rejects any approval)
    submitted -> cancelled    (submitter or owner; rejects any approval)
    draft     -> cancelled    (submitter or owner)
    approved  -> reimbursed   (owner stamps a bill_payment FK)

Approval gating
---------------
At submit time we read setting ``ap.expense_claim_approval_threshold``
(default $200). If ``total_amount >= threshold`` we create a Phase 4.4
``ApprovalRequest`` with ``subject_kind="expense_claim"`` and stamp the
FK on the claim. The claim still flips to ``submitted`` — the approval
queue is decorative; the actual state flip from ``submitted -> approved``
is done by ``approve()`` which checks role at the router layer. When the
approval gate is set, ``approve()`` consumes the request via
``ApprovalsService.mark_consumed``.

Posting (``approve``)
---------------------
Builds a balanced JE: one Dr line per claim line at the line's
expense-account (resolved through ``expense_category.default_expense_
account_id``) and a single Cr to setting
``ap.employee_reimbursable_account_id`` (liability) for the total.
Same-TX guarantee: state flip + JE + event share the caller's
transaction. Any raise rolls back everything.

Reimbursement
-------------
``approved -> reimbursed`` is operator-triggered with a Phase 8.3
``bill_payment_id``. We don't post a JE here — the bill_payment already
debited the Employee-Reimbursable liability when it posted against the
same account. We just stamp the FK and flip state.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ap as ap_events
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.bill_payment import BillPayment
from app.models.expense_claim import (
    ExpenseClaim,
    ExpenseClaimLine,
    ExpenseClaimState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.approvals import ApprovalsService
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExpenseClaimsServiceError(Exception):
    """Base. Routers default to 400."""


class ExpenseClaimNotFoundError(ExpenseClaimsServiceError):
    """Mapped to 404."""


class InvalidExpenseClaimLineError(ExpenseClaimsServiceError):
    """Line failed validation."""


class InvalidExpenseClaimStateError(ExpenseClaimsServiceError):
    """Illegal state transition or attempt to mutate a finalized claim."""


class MissingReimbursableAccountError(ExpenseClaimsServiceError):
    """The ``ap.employee_reimbursable_account_id`` setting isn't set;
    can't approve a claim until the operator configures it."""


class ExpenseCategoryMissingAccountError(ExpenseClaimsServiceError):
    """A line references a category whose
    ``default_expense_account_id`` is unresolvable. Shouldn't happen
    because categories require the column NOT NULL, but defensively
    handled."""


class BillPaymentNotFoundForClaimError(ExpenseClaimsServiceError):
    pass


class InvalidCursorError(ExpenseClaimsServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")
_THRESHOLD_KEY = "ap.expense_claim_approval_threshold"
_REIMBURSABLE_ACCOUNT_KEY = "ap.employee_reimbursable_account_id"


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, claim_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(claim_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


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
            aggregate_type=ap_events.AGGREGATE_TYPE_EXPENSE_CLAIM,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, claim_id: uuid.UUID) -> ExpenseClaim:
    stmt = (
        select(ExpenseClaim)
        .where(ExpenseClaim.id == claim_id)
        .options(selectinload(ExpenseClaim.lines))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ExpenseClaimNotFoundError(str(claim_id))
    return row


def _state(claim: ExpenseClaim) -> ExpenseClaimState:
    return (
        claim.state
        if isinstance(claim.state, ExpenseClaimState)
        else ExpenseClaimState(claim.state)
    )


def _ensure_state(claim: ExpenseClaim, allowed: set[ExpenseClaimState]) -> None:
    current = _state(claim)
    if current not in allowed:
        raise InvalidExpenseClaimStateError(
            f"expense claim {claim.claim_number} is in state {current.value}; "
            f"expected one of {sorted(s.value for s in allowed)}"
        )


# ---------------------------------------------------------------------------
# Line validation
# ---------------------------------------------------------------------------


def _validate_line(raw: dict[str, Any]) -> dict[str, Any]:
    description = (raw.get("description") or "").strip()
    if not description:
        raise InvalidExpenseClaimLineError("line description is required")

    expense_category_id = raw.get("expense_category_id")
    if isinstance(expense_category_id, str):
        try:
            expense_category_id = uuid.UUID(expense_category_id)
        except ValueError as exc:
            raise InvalidExpenseClaimLineError(
                f"invalid expense_category_id: {expense_category_id!r}"
            ) from exc
    if expense_category_id is None:
        raise InvalidExpenseClaimLineError("expense_category_id is required on every line")

    try:
        amount = _q(raw.get("amount", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidExpenseClaimLineError(f"invalid amount on line: {exc}") from exc
    if amount <= _ZERO:
        raise InvalidExpenseClaimLineError("line amount must be positive")

    occurred_on = raw.get("occurred_on")
    if occurred_on is None:
        raise InvalidExpenseClaimLineError("occurred_on is required")
    if isinstance(occurred_on, str):
        from datetime import date as _date_cls

        try:
            occurred_on = _date_cls.fromisoformat(occurred_on)
        except ValueError as exc:
            raise InvalidExpenseClaimLineError(f"invalid occurred_on: {occurred_on!r}") from exc

    attachment_id = raw.get("attachment_id")
    if isinstance(attachment_id, str):
        try:
            attachment_id = uuid.UUID(attachment_id)
        except ValueError as exc:
            raise InvalidExpenseClaimLineError(f"invalid attachment_id: {attachment_id!r}") from exc

    customer_id = raw.get("customer_id")
    if isinstance(customer_id, str):
        try:
            customer_id = uuid.UUID(customer_id)
        except ValueError as exc:
            raise InvalidExpenseClaimLineError(f"invalid customer_id: {customer_id!r}") from exc

    is_billable = bool(raw.get("is_billable", False))
    markup_percent = _q(raw.get("markup_percent", "0"))

    return {
        "expense_category_id": expense_category_id,
        "description": description,
        "amount": amount,
        "occurred_on": occurred_on,
        "attachment_id": attachment_id,
        "is_billable": is_billable,
        "customer_id": customer_id,
        "markup_percent": markup_percent,
    }


def _line_payload(line: ExpenseClaimLine) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "line_number": line.line_number,
        "expense_category_id": str(line.expense_category_id),
        "description": line.description,
        "amount": str(line.amount),
        "occurred_on": line.occurred_on.isoformat(),
        "attachment_id": str(line.attachment_id) if line.attachment_id else None,
        "is_billable": line.is_billable,
        "customer_id": str(line.customer_id) if line.customer_id else None,
        "markup_percent": str(line.markup_percent),
    }


def _recompute_total(claim: ExpenseClaim) -> Decimal:
    total = _ZERO
    for line in claim.lines:
        total = _q(total + _q(line.amount))
    return total


# ---------------------------------------------------------------------------
# Create / update draft
# ---------------------------------------------------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    submitter_user_id: uuid.UUID,
    lines: list[dict[str, Any]] | None = None,
    notes: str | None = None,
    currency: str = "USD",
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    """Allocate ``EXP-YYYY-NNNN`` and create a draft claim."""
    normalized = [_validate_line(line) for line in (lines or [])]

    total = _ZERO
    for line in normalized:
        total = _q(total + line["amount"])

    claim_number = await ReferenceNumberService.allocate("EXP", session=session)

    claim = ExpenseClaim(
        id=uuid.uuid4(),
        claim_number=claim_number,
        submitter_user_id=submitter_user_id,
        state=ExpenseClaimState.DRAFT,
        total_amount=total,
        currency=currency,
        notes=notes,
    )
    session.add(claim)
    await session.flush()

    for idx, line in enumerate(normalized, start=1):
        session.add(
            ExpenseClaimLine(
                id=uuid.uuid4(),
                claim_id=claim.id,
                line_number=idx,
                expense_category_id=line["expense_category_id"],
                description=line["description"],
                amount=line["amount"],
                occurred_on=line["occurred_on"],
                attachment_id=line["attachment_id"],
                is_billable=line["is_billable"],
                customer_id=line["customer_id"],
                markup_percent=line["markup_percent"],
            )
        )
    await session.flush()
    claim = await _load(session, claim.id)

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_CREATED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "claim_number": claim.claim_number,
            "submitter_user_id": str(claim.submitter_user_id),
            "state": _state(claim).value,
            "total_amount": str(claim.total_amount),
            "currency": claim.currency,
            "notes": claim.notes,
            "lines": [
                _line_payload(line) for line in sorted(claim.lines, key=lambda x: x.line_number)
            ],
        },
        actor_user_id=actor_user_id,
    )
    return claim


_EDITABLE_CLAIM_FIELDS = ("notes", "currency")


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def update_draft(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.DRAFT})

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_CLAIM_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        current = getattr(claim, field)
        if current == new_value:
            continue
        before[field] = _serialize(current)
        after[field] = _serialize(new_value)
        setattr(claim, field, new_value)

    items_changed = False
    if "lines" in patch and patch["lines"] is not None:
        items_changed = True
        normalized = [_validate_line(line) for line in patch["lines"]]
        before["lines"] = [
            _line_payload(line) for line in sorted(claim.lines, key=lambda x: x.line_number)
        ]
        for existing in list(claim.lines):
            await session.delete(existing)
        await session.flush()
        claim.lines.clear()
        for idx, line in enumerate(normalized, start=1):
            session.add(
                ExpenseClaimLine(
                    id=uuid.uuid4(),
                    claim_id=claim.id,
                    line_number=idx,
                    expense_category_id=line["expense_category_id"],
                    description=line["description"],
                    amount=line["amount"],
                    occurred_on=line["occurred_on"],
                    attachment_id=line["attachment_id"],
                    is_billable=line["is_billable"],
                    customer_id=line["customer_id"],
                    markup_percent=line["markup_percent"],
                )
            )
        await session.flush()

    if not before and not items_changed:
        return claim

    claim = await _load(session, claim.id)
    claim.total_amount = _recompute_total(claim)
    after["total_amount"] = str(claim.total_amount)
    if items_changed:
        after["lines"] = [
            _line_payload(line) for line in sorted(claim.lines, key=lambda x: x.line_number)
        ]
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_UPDATED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return claim


# ---------------------------------------------------------------------------
# Line-level CRUD (draft only)
# ---------------------------------------------------------------------------


async def add_line(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    line: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.DRAFT})
    normalized = _validate_line(line)
    next_line_number = max((line_obj.line_number for line_obj in claim.lines), default=0) + 1
    session.add(
        ExpenseClaimLine(
            id=uuid.uuid4(),
            claim_id=claim.id,
            line_number=next_line_number,
            expense_category_id=normalized["expense_category_id"],
            description=normalized["description"],
            amount=normalized["amount"],
            occurred_on=normalized["occurred_on"],
            attachment_id=normalized["attachment_id"],
            is_billable=normalized["is_billable"],
            customer_id=normalized["customer_id"],
            markup_percent=normalized["markup_percent"],
        )
    )
    await session.flush()
    claim = await _load(session, claim.id)
    claim.total_amount = _recompute_total(claim)
    await session.flush()
    return claim


async def update_line(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    line_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.DRAFT})
    target = next((line_obj for line_obj in claim.lines if line_obj.id == line_id), None)
    if target is None:
        raise InvalidExpenseClaimLineError(f"line {line_id} not found on claim {claim_id}")
    # Build merged dict so we re-validate the full line.
    merged = {
        "expense_category_id": target.expense_category_id,
        "description": target.description,
        "amount": target.amount,
        "occurred_on": target.occurred_on,
        "attachment_id": target.attachment_id,
        "is_billable": target.is_billable,
        "customer_id": target.customer_id,
        "markup_percent": target.markup_percent,
    }
    merged.update(patch)
    normalized = _validate_line(merged)
    for key, value in normalized.items():
        setattr(target, key, value)
    await session.flush()
    claim = await _load(session, claim.id)
    claim.total_amount = _recompute_total(claim)
    await session.flush()
    return claim


async def delete_line(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    line_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.DRAFT})
    target = next((line_obj for line_obj in claim.lines if line_obj.id == line_id), None)
    if target is None:
        raise InvalidExpenseClaimLineError(f"line {line_id} not found on claim {claim_id}")
    await session.delete(target)
    await session.flush()
    claim = await _load(session, claim.id)
    # Renumber surviving lines to keep them dense.
    for idx, line_obj in enumerate(sorted(claim.lines, key=lambda x: x.line_number), start=1):
        line_obj.line_number = idx
    claim.total_amount = _recompute_total(claim)
    await session.flush()
    return claim


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def submit(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.DRAFT})
    if not claim.lines:
        raise InvalidExpenseClaimStateError(
            f"expense claim {claim.claim_number} has no lines; cannot submit"
        )

    claim.total_amount = _recompute_total(claim)
    claim.state = ExpenseClaimState.SUBMITTED
    claim.submitted_at = datetime.now(UTC)

    threshold = await SettingsService.get(_THRESHOLD_KEY, session=session)
    if threshold is None:
        threshold = Decimal("200.00")
    if not isinstance(threshold, Decimal):
        threshold = Decimal(str(threshold))

    approval_request_id: uuid.UUID | None = None
    if claim.total_amount >= threshold:
        approval = await ApprovalsService.create(
            request_type="ap.expense_claim",
            subject_kind="expense_claim",
            subject_id=claim.id,
            payload={
                "expense_claim_id": str(claim.id),
                "claim_number": claim.claim_number,
                "submitter_user_id": str(claim.submitter_user_id),
                "total_amount": str(claim.total_amount),
            },
            threshold_amount=threshold,
            session=session,
            actor_user_id=actor_user_id,
        )
        claim.approval_request_id = approval.id
        approval_request_id = approval.id

    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_SUBMITTED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "claim_number": claim.claim_number,
            "submitter_user_id": str(claim.submitter_user_id),
            "total_amount": str(claim.total_amount),
            "approval_request_id": (str(approval_request_id) if approval_request_id else None),
        },
        actor_user_id=actor_user_id,
    )
    return claim


async def approve(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    decision_note: str | None = None,
) -> ExpenseClaim:
    """Approve a submitted claim and post the JE in the same TX.

    Dr Expense (per-line, resolved via expense_category) + Cr
    Employee-Reimbursable (setting). The state flip, JE post, approval
    consume-mark, and event all share the caller's transaction.
    """
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.SUBMITTED})

    if not claim.lines:
        raise InvalidExpenseClaimStateError(
            f"expense claim {claim.claim_number} has no lines; cannot approve"
        )

    # QBO is the sole ledger (epic #312, Phase 5e): enqueue a role-tagged
    # JournalEntry (Dr expense per line, Cr employee_reimbursable) via the
    # sync outbox.
    from app.services.quickbooks import outbox as qbo_outbox

    total = _recompute_total(claim)
    claim.total_amount = total

    posted_at = datetime.now(UTC)
    posted_entry_id: uuid.UUID | None = None
    qbo_lines: list[dict] = [
        {"role": "expense", "posting": "debit", "amount": str(_q(line.amount))}
        for line in sorted(claim.lines, key=lambda x: x.line_number)
        if _q(line.amount) > _ZERO
    ]
    if total > _ZERO:
        qbo_lines.append(
            {"role": "employee_reimbursable", "posting": "credit", "amount": str(total)}
        )
    if len(qbo_lines) < 2:
        raise InvalidExpenseClaimStateError(
            f"expense claim {claim.claim_number} has nothing to post (total is zero)"
        )
    await qbo_outbox.enqueue(
        session,
        kind="expense_claim",
        local_id=claim.id,
        payload={"lines": qbo_lines, "private_note": f"Expense claim {claim.claim_number}"},
        op="post",
    )

    claim.posting_journal_entry_id = posted_entry_id
    claim.state = ExpenseClaimState.APPROVED
    claim.approved_at = posted_at
    claim.approver_user_id = actor_user_id
    await session.flush()

    if claim.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == claim.approval_request_id)
            )
        ).scalar_one_or_none()
        if approval is not None and approval.state == ApprovalState.PENDING.value:
            await ApprovalsService.approve(
                approval.id,
                session=session,
                approver_user_id=actor_user_id,
                decision_note=decision_note,
            )
            await ApprovalsService.mark_consumed(approval.id, session=session)

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_APPROVED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "claim_number": claim.claim_number,
            "submitter_user_id": str(claim.submitter_user_id),
            "approver_user_id": str(actor_user_id),
            "total_amount": str(total),
            "journal_entry_id": str(posted_entry_id) if posted_entry_id else None,
        },
        actor_user_id=actor_user_id,
    )
    return claim


async def reject(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    rejection_reason: str | None,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.SUBMITTED})
    claim.state = ExpenseClaimState.REJECTED
    claim.rejection_reason = rejection_reason
    claim.approver_user_id = actor_user_id
    await session.flush()

    if claim.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == claim.approval_request_id)
            )
        ).scalar_one_or_none()
        if approval is not None and approval.state == ApprovalState.PENDING.value:
            await ApprovalsService.reject(
                approval.id,
                session=session,
                approver_user_id=actor_user_id,
                decision_note=rejection_reason,
            )

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_REJECTED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "claim_number": claim.claim_number,
            "submitter_user_id": str(claim.submitter_user_id),
            "approver_user_id": str(actor_user_id),
            "rejection_reason": rejection_reason,
        },
        actor_user_id=actor_user_id,
    )
    return claim


async def cancel(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.DRAFT, ExpenseClaimState.SUBMITTED})
    claim.state = ExpenseClaimState.CANCELLED
    await session.flush()

    if claim.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == claim.approval_request_id)
            )
        ).scalar_one_or_none()
        if approval is not None and approval.state == ApprovalState.PENDING.value:
            await ApprovalsService.cancel(
                approval.id,
                session=session,
                actor_user_id=actor_user_id,
                actor_is_owner=True,
            )

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_CANCELLED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "claim_number": claim.claim_number,
            "submitter_user_id": str(claim.submitter_user_id),
        },
        actor_user_id=actor_user_id,
    )
    return claim


async def mark_reimbursed(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    bill_payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> ExpenseClaim:
    claim = await _load(session, claim_id)
    _ensure_state(claim, {ExpenseClaimState.APPROVED})

    bp = (
        await session.execute(select(BillPayment).where(BillPayment.id == bill_payment_id))
    ).scalar_one_or_none()
    if bp is None:
        raise BillPaymentNotFoundForClaimError(f"bill_payment {bill_payment_id} not found")

    claim.reimbursement_payment_id = bill_payment_id
    claim.state = ExpenseClaimState.REIMBURSED
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_EXPENSE_CLAIM_REIMBURSED,
        aggregate_id=claim.id,
        payload={
            "expense_claim_id": str(claim.id),
            "claim_number": claim.claim_number,
            "submitter_user_id": str(claim.submitter_user_id),
            "bill_payment_id": str(bill_payment_id),
        },
        actor_user_id=actor_user_id,
    )
    return claim


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, claim_id: uuid.UUID) -> ExpenseClaim:
    return await _load(session, claim_id)


@dataclass
class ExpenseClaimPage:
    items: list[ExpenseClaim]
    next_cursor: str | None


async def list_claims(
    session: AsyncSession,
    *,
    submitter_user_id: uuid.UUID | None = None,
    state: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> ExpenseClaimPage:
    stmt = select(ExpenseClaim).options(selectinload(ExpenseClaim.lines))
    if submitter_user_id is not None:
        stmt = stmt.where(ExpenseClaim.submitter_user_id == submitter_user_id)
    if state is not None:
        try:
            stmt = stmt.where(ExpenseClaim.state == ExpenseClaimState(state))
        except ValueError as exc:
            raise ExpenseClaimsServiceError(f"invalid state filter: {state!r}") from exc
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                ExpenseClaim.created_at < anchor_ts,
                and_(ExpenseClaim.created_at == anchor_ts, ExpenseClaim.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(ExpenseClaim.created_at), desc(ExpenseClaim.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return ExpenseClaimPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "BillPaymentNotFoundForClaimError",
    "ExpenseCategoryMissingAccountError",
    "ExpenseClaimNotFoundError",
    "ExpenseClaimPage",
    "ExpenseClaimsServiceError",
    "InvalidCursorError",
    "InvalidExpenseClaimLineError",
    "InvalidExpenseClaimStateError",
    "MissingReimbursableAccountError",
    "add_line",
    "approve",
    "cancel",
    "create_draft",
    "delete_line",
    "get",
    "list_claims",
    "mark_reimbursed",
    "reject",
    "submit",
    "update_draft",
    "update_line",
]


# ---------------------------------------------------------------------------
# Subject-resolver registration (Phase 4.4 approvals integration)
# ---------------------------------------------------------------------------
try:  # pragma: no cover
    from app.services import approvals as _approvals_module

    if hasattr(_approvals_module, "register_subject_resolver"):

        async def _resolver(subject_id: uuid.UUID, session: AsyncSession) -> ExpenseClaim:
            return await get(session, subject_id)

        _approvals_module.register_subject_resolver("expense_claim", _resolver)
except Exception:
    pass


# Quiet unused-import linter — asc is kept for future ordering features
_ = asc
