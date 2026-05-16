"""Email service (Phase 7.7, #115).

Owns the ``email_message`` row lifecycle: enqueue, attempt send, retry,
cancel, worker tick. The provider abstraction (``providers.py``) handles
the wire-level "actually deliver the bytes" concern; this module is
about persistence, state transitions, and retry timing.

State machine
-------------
``queued`` → ``sending`` (in-flight) → ``sent`` | ``failed`` | ``queued``
(scheduled retry). ``cancel`` is only legal from ``queued``. ``bounced``
is reserved for the future SES/postmark path; today no code transitions
into it.

Retry curve
-----------
Six attempts, exponential: 60s, 300s, 900s, 3600s, 21600s, then give up.
That's roughly 1m / 5m / 15m / 1h / 6h with a final ``failed`` state.
The values are tuned so a transient SMTP outage gets a few quick retries
and a long-running incident still gets one slow re-attempt before we
hand it to the operator via ``last_error``.

Idempotency
-----------
``enqueue_email`` is replay-safe: it checks the
``(kind, subject_kind, subject_id)`` unique partial index before
inserting, so re-emitting an upstream event for the same subject is a
no-op. ``IntegrityError`` is also caught for the race condition where
two replayers fire at the same instant.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ar as ar_events
from app.models.email_message import EmailKind, EmailMessage, EmailState
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.email.providers import (
    Attachment,
    EmailProvider,
    get_email_provider,
)
from app.services.files import write_blob

log = logging.getLogger(__name__)

# Retry backoff schedule in seconds. Indexed by the upcoming attempt number
# (so ``backoff_seconds(1)`` is the wait before attempt #2). After
# ``len(BACKOFF)`` failures we give up and mark the row ``failed``.
BACKOFF: tuple[int, ...] = (60, 300, 900, 3600, 21600)
MAX_ATTEMPTS = len(BACKOFF) + 1  # 6


def max_attempts() -> int:
    return MAX_ATTEMPTS


def backoff_seconds(next_attempt: int) -> int:
    """Seconds to wait before ``next_attempt`` (1-indexed past the failed try).

    Caller passes the count of already-failed attempts. The result is
    used to stamp ``next_retry_at = now + backoff``. Returns the last
    bucket's value if asked beyond the curve (caller will normally
    short-circuit to ``failed`` before reaching that).
    """
    if next_attempt <= 0:
        return BACKOFF[0]
    idx = min(next_attempt - 1, len(BACKOFF) - 1)
    return BACKOFF[idx]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EmailServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class EmailMessageNotFoundError(EmailServiceError):
    """Mapped to 404."""


class InvalidEmailStateError(EmailServiceError):
    """Illegal state transition (cancel-after-sent, retry-from-sent, etc.)."""


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def body_storage_key(email_id: uuid.UUID) -> str:
    return f"emails/{email_id}/body.html"


def attachment_storage_key(email_id: uuid.UUID, filename: str) -> str:
    # Replace path separators to keep the file under the email-id prefix.
    safe = filename.replace("/", "_").replace("\\", "_")
    return f"emails/{email_id}/attachments/{safe}"


async def _resolve_storage_root(*, session: AsyncSession):
    from pathlib import Path

    from app.services.settings.service import SettingsService

    raw = await SettingsService.get("email.storage_root", session=session)
    return Path(str(raw))


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=ar_events.AGGREGATE_TYPE_EMAIL,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


async def enqueue_email(
    kind: EmailKind | str,
    *,
    subject_kind: str | None,
    subject_id: uuid.UUID | None,
    to_address: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    attachments: list[Attachment] | None = None,
    session: AsyncSession,
    from_address: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> EmailMessage | None:
    """Create a queued ``email_message`` row + persist body & attachments.

    Returns ``None`` when an existing row already covers this subject —
    that's the idempotency contract. Callers (dispatcher, manual-send
    endpoints) treat ``None`` as success.
    """
    kind_enum = kind if isinstance(kind, EmailKind) else EmailKind(kind)
    attachments = list(attachments or [])

    # Idempotency: pre-check the unique partial index. The DB still has
    # the final word via the integrity error catch below, but most calls
    # hit the cached result path.
    if subject_id is not None and subject_kind is not None:
        existing_stmt = select(EmailMessage).where(
            EmailMessage.kind == kind_enum,
            EmailMessage.subject_kind == subject_kind,
            EmailMessage.subject_id == subject_id,
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return None

    from app.services.settings.service import SettingsService

    if from_address is None:
        from_address = str(await SettingsService.get("email.from_address", session=session))

    email = EmailMessage(
        id=uuid.uuid4(),
        kind=kind_enum,
        subject_kind=subject_kind,
        subject_id=subject_id,
        to_address=to_address,
        from_address=from_address,
        subject=subject,
        body_html_storage_key=body_storage_key(uuid.uuid4()),  # tmp; rewrite below
        state=EmailState.QUEUED,
        attempts=0,
        next_retry_at=datetime.now(UTC),
    )
    email.body_html_storage_key = body_storage_key(email.id)

    # Persist body + attachments to storage BEFORE inserting the row so a
    # partial write doesn't leave a dangling queued row pointing at
    # nothing.
    root = await _resolve_storage_root(session=session)
    write_blob(body_html.encode("utf-8"), root=root, storage_key=email.body_html_storage_key)
    attachments_meta: list[dict[str, str]] = []
    for att in attachments:
        key = attachment_storage_key(email.id, att.filename)
        write_blob(att.content, root=root, storage_key=key)
        attachments_meta.append({"filename": att.filename, "storage_key": key})
    email.attachments_json = attachments_meta or None

    session.add(email)
    try:
        await session.flush()
    except IntegrityError:
        # Lost a race with another writer on the partial unique index.
        # Treat as a no-op for replay safety.
        await session.rollback()
        return None

    await _emit(
        session,
        event_type=ar_events.TYPE_EMAIL_QUEUED,
        aggregate_id=email.id,
        payload={
            "email_id": str(email.id),
            "kind": kind_enum.value,
            "subject_kind": subject_kind,
            "subject_id": str(subject_id) if subject_id else None,
            "to_address": to_address,
            "subject": subject,
        },
        actor_user_id=actor_user_id,
    )
    return email


# ---------------------------------------------------------------------------
# attempt_send
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, email_id: uuid.UUID) -> EmailMessage:
    row = (
        await session.execute(select(EmailMessage).where(EmailMessage.id == email_id))
    ).scalar_one_or_none()
    if row is None:
        raise EmailMessageNotFoundError(str(email_id))
    return row


async def _read_attachments(email: EmailMessage, *, session: AsyncSession) -> list[Attachment]:
    """Reconstruct the :class:`Attachment` list from storage."""
    if not email.attachments_json:
        return []
    from app.services.files import read_blob

    root = await _resolve_storage_root(session=session)
    out: list[Attachment] = []
    for entry in email.attachments_json:
        blob = read_blob(entry["storage_key"], root=root)
        if blob is None:
            log.warning(
                "email.attachment_missing",
                extra={"email_id": str(email.id), "key": entry["storage_key"]},
            )
            continue
        out.append(Attachment(filename=entry["filename"], content=blob))
    return out


async def _read_body(email: EmailMessage, *, session: AsyncSession) -> str:
    from app.services.files import read_blob

    root = await _resolve_storage_root(session=session)
    raw = read_blob(email.body_html_storage_key, root=root)
    return raw.decode("utf-8") if raw is not None else ""


async def attempt_send(
    email_id: uuid.UUID,
    *,
    session: AsyncSession,
    provider: EmailProvider | None = None,
) -> EmailMessage:
    """Try to deliver one queued row.

    Walks: load → check state → mark sending → invoke provider →
    success/failure → state + retry stamp + event. On exception the row
    state flips to ``queued`` with ``next_retry_at`` advanced, OR to
    ``failed`` when the attempt budget is exhausted.
    """
    email = await _load(session, email_id)
    if email.state == EmailState.SENT:
        return email
    if email.state in (EmailState.FAILED, EmailState.BOUNCED):
        raise InvalidEmailStateError(f"email {email_id} is in terminal state {email.state.value}")
    if email.state == EmailState.SENDING:
        # Another worker is already processing it. Skip.
        return email

    email.state = EmailState.SENDING
    await session.flush()

    if provider is None:
        provider = await get_email_provider(session=session)

    body_html = await _read_body(email, session=session)
    attachments = await _read_attachments(email, session=session)

    try:
        result = await provider.send(
            to=email.to_address,
            subject=email.subject,
            body_html=body_html,
            body_text=None,
            attachments=attachments,
            from_address=email.from_address,
        )
    except Exception as exc:
        email.attempts += 1
        email.last_error = str(exc)[:2000]
        if email.attempts >= MAX_ATTEMPTS:
            email.state = EmailState.FAILED
            email.next_retry_at = None
            await session.flush()
            await _emit(
                session,
                event_type=ar_events.TYPE_EMAIL_FAILED,
                aggregate_id=email.id,
                payload={
                    "email_id": str(email.id),
                    "kind": email.kind.value,
                    "subject_kind": email.subject_kind,
                    "subject_id": str(email.subject_id) if email.subject_id else None,
                    "attempts": email.attempts,
                    "last_error": email.last_error or "",
                },
            )
        else:
            email.state = EmailState.QUEUED
            email.next_retry_at = datetime.now(UTC) + timedelta(
                seconds=backoff_seconds(email.attempts)
            )
            await session.flush()
        return email

    email.attempts += 1
    email.state = EmailState.SENT
    email.sent_at = datetime.now(UTC)
    email.provider_message_id = result.provider_message_id
    email.next_retry_at = None
    email.last_error = None
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_EMAIL_SENT,
        aggregate_id=email.id,
        payload={
            "email_id": str(email.id),
            "kind": email.kind.value,
            "subject_kind": email.subject_kind,
            "subject_id": str(email.subject_id) if email.subject_id else None,
            "provider_message_id": email.provider_message_id,
            "sent_at": email.sent_at.isoformat(),
        },
    )
    return email


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


async def cancel(
    email_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> EmailMessage:
    """Cancel a queued email. Illegal once the row is non-queued."""
    email = await _load(session, email_id)
    if email.state != EmailState.QUEUED:
        raise InvalidEmailStateError(f"cannot cancel email {email_id} in state {email.state.value}")
    email.state = EmailState.FAILED
    email.last_error = "cancelled by operator"
    email.next_retry_at = None
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_EMAIL_CANCELLED,
        aggregate_id=email.id,
        payload={
            "email_id": str(email.id),
            "kind": email.kind.value,
        },
        actor_user_id=actor_user_id,
    )
    return email


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------


async def run_worker_once(
    *,
    session: AsyncSession,
    provider: EmailProvider | None = None,
    limit: int = 50,
) -> list[EmailMessage]:
    """Drive every queued row whose ``next_retry_at`` is due.

    Intended for the ``*/1 * * * *`` cron job. Returns the rows that
    were touched (in any direction) so an operator UI / test can inspect
    progress. The caller owns commit.
    """
    now = datetime.now(UTC)
    stmt = (
        select(EmailMessage)
        .where(EmailMessage.state == EmailState.QUEUED)
        .where((EmailMessage.next_retry_at.is_(None)) | (EmailMessage.next_retry_at <= now))
        .order_by(EmailMessage.created_at.asc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    touched: list[EmailMessage] = []
    for row in rows:
        updated = await attempt_send(row.id, session=session, provider=provider)
        touched.append(updated)
    return touched


# ---------------------------------------------------------------------------
# Manual retry
# ---------------------------------------------------------------------------


async def retry(
    email_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None = None,
) -> EmailMessage:
    """Operator-triggered retry. Moves ``failed`` → ``queued`` with a
    fresh attempt counter so the worker picks it up immediately.

    Re-attempting an already-``sent`` row is a no-op (returns as-is)
    rather than a 400 — that keeps the UI's "retry" button idempotent.
    """
    email = await _load(session, email_id)
    if email.state == EmailState.SENT:
        return email
    if email.state == EmailState.QUEUED:
        # Already pending; just stamp next_retry_at to now and return.
        email.next_retry_at = datetime.now(UTC)
        await session.flush()
        return email
    email.state = EmailState.QUEUED
    email.attempts = 0
    email.next_retry_at = datetime.now(UTC)
    email.last_error = None
    await session.flush()
    return email


__all__ = [
    "BACKOFF",
    "EmailMessageNotFoundError",
    "EmailServiceError",
    "InvalidEmailStateError",
    "attempt_send",
    "backoff_seconds",
    "cancel",
    "enqueue_email",
    "max_attempts",
    "retry",
    "run_worker_once",
]
