"""Attachments service (Phase 2.6).

Upload/download/archive/list for polymorphic file attachments. Files
live on local disk under the ``attachments.storage_root`` setting; rows
in the ``attachment`` table carry filename + mime + size + relative
storage path.

Permission rules:
* Any authenticated non-viewer can ``upload``.
* All authenticated users can ``list_for`` and ``download``.
* ``archive``: uploader OR owner.

MIME allowlist: ``image/*``, ``application/pdf``, ``text/plain``,
``text/markdown``, ``application/vnd.openxmlformats-officedocument.*``.
Size limit: 10 MB.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import notes_attachments as events
from app.models.attachment import Attachment
from app.models.auth import Role, User
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.attachments.storage import (
    compute_storage_path,
    resolve_storage_root,
    safe_write,
)

# 10 MB cap per upload.
MAX_BYTE_SIZE: int = 10 * 1024 * 1024

# Explicit allowlist of full mime types we accept verbatim.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
    }
)
# Prefix-based allowlist: any mime starting with one of these is accepted.
ALLOWED_MIME_PREFIXES: tuple[str, ...] = (
    "image/",
    "application/vnd.openxmlformats-officedocument.",
)


class AttachmentsServiceError(Exception):
    """Base. Routers map to 400 unless a more specific subclass matches."""


class AttachmentNotFoundError(AttachmentsServiceError):
    pass


class AttachmentPermissionError(AttachmentsServiceError):
    pass


class InvalidMimeTypeError(AttachmentsServiceError):
    """Mime type not on the allowlist (router → 415)."""


class OversizeAttachmentError(AttachmentsServiceError):
    """Upload exceeded :data:`MAX_BYTE_SIZE` (router → 413)."""


class InvalidCursorError(AttachmentsServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mime_is_allowed(mime_type: str) -> bool:
    if mime_type in ALLOWED_MIME_TYPES:
        return True
    return any(mime_type.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES)


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
            aggregate_type=events.AGGREGATE_TYPE_ATTACHMENT,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, attachment_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(attachment_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, attachment_id: uuid.UUID) -> Attachment:
    row = (
        await session.execute(select(Attachment).where(Attachment.id == attachment_id))
    ).scalar_one_or_none()
    if row is None:
        raise AttachmentNotFoundError(str(attachment_id))
    return row


@dataclass
class UploadedFile:
    filename: str
    mime_type: str
    content: bytes


async def upload(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    file: UploadedFile,
    actor: User,
) -> Attachment:
    """Persist ``file`` to local disk and create the matching row.

    The row write and the event append happen in the caller's
    transaction. The on-disk file is written BEFORE the row + event so
    that if the transaction rolls back we have an orphan file (rare,
    swept later) rather than a row pointing at a missing file (broken
    download invariant).
    """
    mime = (file.mime_type or "application/octet-stream").strip()
    if not _mime_is_allowed(mime):
        raise InvalidMimeTypeError(f"mime type {mime!r} is not allowed")
    if len(file.content) > MAX_BYTE_SIZE:
        raise OversizeAttachmentError(
            f"attachment size {len(file.content)} exceeds limit {MAX_BYTE_SIZE}"
        )

    rel_path = compute_storage_path(file.filename)
    root = await resolve_storage_root(session=session)
    dest = root / rel_path
    safe_write(file.content, dest)

    attachment = Attachment(
        entity_kind=entity_kind,
        entity_id=entity_id,
        filename=file.filename,
        mime_type=mime,
        byte_size=len(file.content),
        storage_path=rel_path,
        uploaded_by_user_id=actor.id,
        is_archived=False,
    )
    session.add(attachment)
    await session.flush()

    await _emit(
        session,
        event_type=events.TYPE_ATTACHMENT_UPLOADED,
        aggregate_id=attachment.id,
        payload={
            "attachment_id": str(attachment.id),
            "entity_kind": entity_kind,
            "entity_id": str(entity_id),
            "filename": file.filename,
            "mime_type": mime,
            "byte_size": len(file.content),
        },
        actor_user_id=actor.id,
    )
    return attachment


@dataclass
class DownloadPayload:
    content: bytes
    mime_type: str
    filename: str


async def download(session: AsyncSession, attachment_id: uuid.UUID) -> DownloadPayload:
    """Read the on-disk bytes for ``attachment_id`` and return them.

    Returns the full content as bytes — these files are capped at 10 MB
    so streaming gains us nothing operationally. The router wraps this
    in a StreamingResponse to stay consistent with the spec.
    """
    attachment = await get(session, attachment_id)
    root = await resolve_storage_root(session=session)
    path: Path = root / attachment.storage_path
    with open(path, "rb") as fh:
        content = fh.read()
    return DownloadPayload(
        content=content,
        mime_type=attachment.mime_type,
        filename=attachment.filename,
    )


async def archive(
    session: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    actor: User,
) -> Attachment:
    attachment = await get(session, attachment_id)
    if attachment.uploaded_by_user_id != actor.id and actor.role != Role.OWNER:
        raise AttachmentPermissionError("only the uploader or an owner can archive this attachment")
    if attachment.is_archived:
        return attachment
    attachment.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=events.TYPE_ATTACHMENT_ARCHIVED,
        aggregate_id=attachment.id,
        payload={"attachment_id": str(attachment.id)},
        actor_user_id=actor.id,
    )
    return attachment


@dataclass
class AttachmentPage:
    items: list[Attachment]
    next_cursor: str | None


async def list_for(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    include_archived: bool = False,
    cursor: str | None = None,
    limit: int = 50,
) -> AttachmentPage:
    stmt = (
        select(Attachment)
        .where(Attachment.entity_kind == entity_kind)
        .where(Attachment.entity_id == entity_id)
    )
    if not include_archived:
        stmt = stmt.where(Attachment.is_archived.is_(False))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Attachment.created_at < anchor_ts,
                and_(Attachment.created_at == anchor_ts, Attachment.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Attachment.created_at), desc(Attachment.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return AttachmentPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "ALLOWED_MIME_PREFIXES",
    "ALLOWED_MIME_TYPES",
    "AttachmentNotFoundError",
    "AttachmentPage",
    "AttachmentPermissionError",
    "AttachmentsServiceError",
    "DownloadPayload",
    "InvalidCursorError",
    "InvalidMimeTypeError",
    "MAX_BYTE_SIZE",
    "OversizeAttachmentError",
    "UploadedFile",
    "archive",
    "download",
    "get",
    "list_for",
    "upload",
]
