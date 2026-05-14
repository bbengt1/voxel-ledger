"""Notes service (Phase 2.6).

Polymorphic notes attached to any catalog entity. Permission rules:

* Any authenticated non-viewer role can ``create``.
* ``update`` / ``delete``: the author OR an owner.
* ``pin`` / ``unpin``: owner only.

Every mutation appends a typed ``platform.Note*`` event inside the same
transaction as the row write. Bodies are never put in event payloads in
full — only a 100-char preview, in line with the excerpt whitelist.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import notes_attachments as notes_events
from app.models.auth import Role, User
from app.models.note import Note
from app.schemas.events import EventCreate
from app.services import event_store


class NotesServiceError(Exception):
    """Base. Routers map to 400 unless a more specific subclass matches."""


class NoteNotFoundError(NotesServiceError):
    pass


class NotePermissionError(NotesServiceError):
    """Acting user is not allowed to take this action on this note."""


class InvalidCursorError(NotesServiceError):
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
            aggregate_type=notes_events.AGGREGATE_TYPE_NOTE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, note_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(note_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


def _is_author_or_owner(note: Note, actor: User) -> bool:
    return note.author_user_id == actor.id or actor.role == Role.OWNER


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, note_id: uuid.UUID) -> Note:
    row = (await session.execute(select(Note).where(Note.id == note_id))).scalar_one_or_none()
    if row is None:
        raise NoteNotFoundError(str(note_id))
    return row


async def create(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    body: str,
    author: User,
) -> Note:
    body = body.strip()
    if not body:
        raise NotesServiceError("note body must not be empty")
    note = Note(
        entity_kind=entity_kind,
        entity_id=entity_id,
        body=body,
        author_user_id=author.id,
        is_pinned=False,
    )
    session.add(note)
    await session.flush()
    await _emit(
        session,
        event_type=notes_events.TYPE_NOTE_CREATED,
        aggregate_id=note.id,
        payload={
            "note_id": str(note.id),
            "entity_kind": entity_kind,
            "entity_id": str(entity_id),
            "author_user_id": str(author.id),
            "body_preview": notes_events.body_preview(body),
        },
        actor_user_id=author.id,
    )
    return note


async def update(
    session: AsyncSession,
    *,
    note_id: uuid.UUID,
    body: str,
    actor: User,
) -> Note:
    note = await get(session, note_id)
    if not _is_author_or_owner(note, actor):
        raise NotePermissionError("only the author or an owner can update this note")
    new_body = body.strip()
    if not new_body:
        raise NotesServiceError("note body must not be empty")
    if new_body == note.body:
        return note
    old_preview = notes_events.body_preview(note.body)
    note.body = new_body
    await session.flush()
    await _emit(
        session,
        event_type=notes_events.TYPE_NOTE_UPDATED,
        aggregate_id=note.id,
        payload={
            "note_id": str(note.id),
            "body_preview_before": old_preview,
            "body_preview_after": notes_events.body_preview(new_body),
        },
        actor_user_id=actor.id,
    )
    return note


async def delete(
    session: AsyncSession,
    *,
    note_id: uuid.UUID,
    actor: User,
) -> None:
    note = await get(session, note_id)
    if not _is_author_or_owner(note, actor):
        raise NotePermissionError("only the author or an owner can delete this note")
    payload = {
        "note_id": str(note.id),
        "entity_kind": note.entity_kind,
        "entity_id": str(note.entity_id),
    }
    await session.delete(note)
    await session.flush()
    await _emit(
        session,
        event_type=notes_events.TYPE_NOTE_DELETED,
        aggregate_id=note.id,
        payload=payload,
        actor_user_id=actor.id,
    )


async def pin(
    session: AsyncSession,
    *,
    note_id: uuid.UUID,
    actor: User,
) -> Note:
    if actor.role != Role.OWNER:
        raise NotePermissionError("only an owner can pin a note")
    note = await get(session, note_id)
    if note.is_pinned:
        return note
    note.is_pinned = True
    await session.flush()
    await _emit(
        session,
        event_type=notes_events.TYPE_NOTE_PINNED,
        aggregate_id=note.id,
        payload={"note_id": str(note.id)},
        actor_user_id=actor.id,
    )
    return note


async def unpin(
    session: AsyncSession,
    *,
    note_id: uuid.UUID,
    actor: User,
) -> Note:
    if actor.role != Role.OWNER:
        raise NotePermissionError("only an owner can unpin a note")
    note = await get(session, note_id)
    if not note.is_pinned:
        return note
    note.is_pinned = False
    await session.flush()
    await _emit(
        session,
        event_type=notes_events.TYPE_NOTE_UNPINNED,
        aggregate_id=note.id,
        payload={"note_id": str(note.id)},
        actor_user_id=actor.id,
    )
    return note


@dataclass
class NotePage:
    items: list[Note]
    next_cursor: str | None


async def list_for(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 50,
) -> NotePage:
    """List notes for a given polymorphic ref.

    Pinned first, then chronological newest-first. Cursor is on
    ``(created_at, id)`` strictly less than the anchor — pinned notes
    sort alongside their created_at within the same query so the cursor
    semantics stay simple.
    """
    stmt = select(Note).where(Note.entity_kind == entity_kind).where(Note.entity_id == entity_id)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Note.created_at < anchor_ts,
                and_(Note.created_at == anchor_ts, Note.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Note.is_pinned), desc(Note.created_at), desc(Note.id)).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return NotePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidCursorError",
    "NoteNotFoundError",
    "NotePage",
    "NotePermissionError",
    "NotesServiceError",
    "create",
    "delete",
    "get",
    "list_for",
    "pin",
    "unpin",
    "update",
]
