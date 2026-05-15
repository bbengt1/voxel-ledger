"""Approvals service (Phase 4.4, #67).

Generic request / approve / reject / cancel queue. Consumers (Phase 4.2
journal-entry threshold gating is the first; refunds and period-close
finalization follow) route through here when an action requires an
out-of-band sign-off.

The full proposed payload lives on the ``approval_request`` row. Events
only carry a short ``payload_summary`` (~100 chars) — keeping sensitive
contents out of the event log and audit projection.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import approvals as approval_events
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ApprovalsServiceError(Exception):
    """Base. Routers default to 400."""


class ApprovalRequestNotFoundError(ApprovalsServiceError):
    pass


class ApprovalAlreadyDecidedError(ApprovalsServiceError):
    """Request is not in the ``pending`` state."""


class SelfApprovalError(ApprovalsServiceError):
    """The approver/rejecter is the original requester."""


class ApprovalCancelForbiddenError(ApprovalsServiceError):
    """Only the requester or an owner may cancel a pending request."""


class ApprovalNotApprovedError(ApprovalsServiceError):
    """``mark_consumed`` was called on a non-approved request."""


class ApprovalAlreadyConsumedError(ApprovalsServiceError):
    """``mark_consumed`` was called on an already-consumed request."""


class InvalidCursorError(ApprovalsServiceError):
    pass


# ---------------------------------------------------------------------------
# Pagination cursor — (requested_at DESC, id DESC)
# ---------------------------------------------------------------------------


def _encode_cursor(requested_at: datetime, request_id: uuid.UUID) -> str:
    raw = json.dumps({"t": requested_at.isoformat(), "i": str(request_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return (
            datetime.fromisoformat(decoded["t"]),
            uuid.UUID(decoded["i"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_payload(request_type: str, subject_kind: str, payload: dict[str, Any]) -> str:
    """Build a short, non-sensitive summary string for the event payload.

    We intentionally do NOT include the full payload here — that lives on
    the row and is surfaced through the API to authorized callers only.
    The summary is bounded to ~100 chars and references only the
    request_type / subject_kind so secrets in the payload can't leak via
    the event log or audit projection.
    """
    summary = f"{request_type} on {subject_kind}"
    return summary[:100]


def _preview(text: str | None) -> str | None:
    if text is None:
        return None
    return text[:100]


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
            aggregate_type=approval_events.AGGREGATE_TYPE_APPROVAL_REQUEST,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


@dataclass
class ApprovalRequestPage:
    items: list[ApprovalRequest]
    next_cursor: str | None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ApprovalsService:
    """Static methods on a namespace class, mirroring SettingsService."""

    @staticmethod
    async def create(
        request_type: str,
        subject_kind: str,
        subject_id: uuid.UUID,
        payload: dict[str, Any],
        threshold_amount: Decimal | None = None,
        *,
        session: AsyncSession,
        actor_user_id: uuid.UUID,
    ) -> ApprovalRequest:
        """Insert a fresh ``pending`` request and emit ApprovalRequested."""
        row = ApprovalRequest(
            id=uuid.uuid4(),
            request_type=request_type,
            subject_kind=subject_kind,
            subject_id=subject_id,
            requested_by_user_id=actor_user_id,
            requested_at=datetime.now(UTC),
            state=ApprovalState.PENDING.value,
            payload=payload,
            threshold_amount=threshold_amount,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)

        await _emit(
            session,
            event_type=approval_events.TYPE_APPROVAL_REQUESTED,
            aggregate_id=row.id,
            payload={
                "request_id": str(row.id),
                "request_type": request_type,
                "subject_kind": subject_kind,
                "subject_id": str(subject_id),
                "requested_by_user_id": str(actor_user_id),
                "payload_summary": _summarize_payload(request_type, subject_kind, payload),
                "threshold_amount": (
                    str(threshold_amount) if threshold_amount is not None else None
                ),
            },
            actor_user_id=actor_user_id,
        )

        return row

    @staticmethod
    async def get(request_id: uuid.UUID, *, session: AsyncSession) -> ApprovalRequest:
        stmt = select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ApprovalRequestNotFoundError(str(request_id))
        return row

    @staticmethod
    async def _load_pending(request_id: uuid.UUID, *, session: AsyncSession) -> ApprovalRequest:
        row = await ApprovalsService.get(request_id, session=session)
        if row.state != ApprovalState.PENDING.value:
            raise ApprovalAlreadyDecidedError(
                f"approval request {request_id} is {row.state}, not pending"
            )
        return row

    @staticmethod
    async def approve(
        request_id: uuid.UUID,
        *,
        session: AsyncSession,
        approver_user_id: uuid.UUID,
        decision_note: str | None = None,
    ) -> ApprovalRequest:
        row = await ApprovalsService._load_pending(request_id, session=session)
        if row.requested_by_user_id == approver_user_id:
            raise SelfApprovalError("the requester cannot approve their own approval request")
        row.state = ApprovalState.APPROVED.value
        row.decided_by_user_id = approver_user_id
        row.decided_at = datetime.now(UTC)
        row.decision_note = decision_note
        await session.flush()
        await session.refresh(row)

        await _emit(
            session,
            event_type=approval_events.TYPE_APPROVAL_APPROVED,
            aggregate_id=row.id,
            payload={
                "request_id": str(row.id),
                "approver_user_id": str(approver_user_id),
                "decision_note_preview": _preview(decision_note),
            },
            actor_user_id=approver_user_id,
        )
        return row

    @staticmethod
    async def reject(
        request_id: uuid.UUID,
        *,
        session: AsyncSession,
        approver_user_id: uuid.UUID,
        decision_note: str | None = None,
    ) -> ApprovalRequest:
        row = await ApprovalsService._load_pending(request_id, session=session)
        if row.requested_by_user_id == approver_user_id:
            raise SelfApprovalError("the requester cannot reject their own approval request")
        row.state = ApprovalState.REJECTED.value
        row.decided_by_user_id = approver_user_id
        row.decided_at = datetime.now(UTC)
        row.decision_note = decision_note
        await session.flush()
        await session.refresh(row)

        await _emit(
            session,
            event_type=approval_events.TYPE_APPROVAL_REJECTED,
            aggregate_id=row.id,
            payload={
                "request_id": str(row.id),
                "approver_user_id": str(approver_user_id),
                "decision_note_preview": _preview(decision_note),
            },
            actor_user_id=approver_user_id,
        )
        return row

    @staticmethod
    async def cancel(
        request_id: uuid.UUID,
        *,
        session: AsyncSession,
        actor_user_id: uuid.UUID,
        actor_is_owner: bool = False,
        reason: str | None = None,
    ) -> ApprovalRequest:
        """Cancel a pending request.

        Allowed: the original requester, or an owner. The endpoint passes
        ``actor_is_owner`` rather than the service re-querying roles, to
        keep this layer free of identity concerns.
        """
        row = await ApprovalsService._load_pending(request_id, session=session)
        if not (actor_is_owner or row.requested_by_user_id == actor_user_id):
            raise ApprovalCancelForbiddenError(
                "only the requester or an owner may cancel an approval request"
            )
        row.state = ApprovalState.CANCELLED.value
        row.decided_by_user_id = actor_user_id
        row.decided_at = datetime.now(UTC)
        row.decision_note = reason
        await session.flush()
        await session.refresh(row)

        await _emit(
            session,
            event_type=approval_events.TYPE_APPROVAL_CANCELLED,
            aggregate_id=row.id,
            payload={
                "request_id": str(row.id),
                "cancelled_by_user_id": str(actor_user_id),
            },
            actor_user_id=actor_user_id,
        )
        return row

    @staticmethod
    async def mark_consumed(request_id: uuid.UUID, *, session: AsyncSession) -> ApprovalRequest:
        """Idempotency aid for downstream consumers.

        Must be ``approved`` and not previously consumed. No event is
        emitted — this is purely a flag preventing double-dispatch.
        """
        row = await ApprovalsService.get(request_id, session=session)
        if row.state != ApprovalState.APPROVED.value:
            raise ApprovalNotApprovedError(
                f"approval request {request_id} is {row.state}, not approved"
            )
        if row.consumed_at is not None:
            raise ApprovalAlreadyConsumedError(
                f"approval request {request_id} was already consumed at "
                f"{row.consumed_at.isoformat()}"
            )
        row.consumed_at = datetime.now(UTC)
        await session.flush()
        await session.refresh(row)
        return row

    @staticmethod
    async def list(
        *,
        session: AsyncSession,
        state: str | None = None,
        request_type: str | None = None,
        subject_kind: str | None = None,
        requested_by_user_id: uuid.UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ApprovalRequestPage:
        stmt = select(ApprovalRequest)
        if state is not None:
            stmt = stmt.where(ApprovalRequest.state == state)
        if request_type is not None:
            stmt = stmt.where(ApprovalRequest.request_type == request_type)
        if subject_kind is not None:
            stmt = stmt.where(ApprovalRequest.subject_kind == subject_kind)
        if requested_by_user_id is not None:
            stmt = stmt.where(ApprovalRequest.requested_by_user_id == requested_by_user_id)
        if cursor is not None:
            anchor_ts, anchor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    ApprovalRequest.requested_at < anchor_ts,
                    and_(
                        ApprovalRequest.requested_at == anchor_ts,
                        ApprovalRequest.id < anchor_id,
                    ),
                )
            )
        stmt = stmt.order_by(desc(ApprovalRequest.requested_at), desc(ApprovalRequest.id)).limit(
            limit + 1
        )

        rows = list((await session.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        next_cursor = (
            _encode_cursor(rows[-1].requested_at, rows[-1].id) if (rows and has_more) else None
        )
        return ApprovalRequestPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "ApprovalAlreadyConsumedError",
    "ApprovalAlreadyDecidedError",
    "ApprovalCancelForbiddenError",
    "ApprovalNotApprovedError",
    "ApprovalRequestNotFoundError",
    "ApprovalRequestPage",
    "ApprovalsService",
    "ApprovalsServiceError",
    "InvalidCursorError",
    "SelfApprovalError",
]
