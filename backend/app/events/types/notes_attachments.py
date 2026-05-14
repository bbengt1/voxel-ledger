"""Notes & attachments event types (Phase 2.6).

Polymorphic refs to a host entity (material/supply/rate/product). The
``aggregate_type`` for each event is the kind word — ``note`` or
``attachment`` — and ``aggregate_id`` is the row id.

Excerpt strategy
----------------
Note bodies are intentionally NOT stored in event payloads in full. We
emit a 100-char preview (``body_preview``, ``body_preview_before`` /
``body_preview_after`` on update) so the audit log can render context
without leaking the full markdown. The excerpt whitelist enforces this
at the read-model boundary too.

Attachment payloads carry filename, mime_type, byte_size — never the
file bytes, never ``storage_path``. The storage path is a private detail
of the attachments service.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_NOTE: str = "note"
AGGREGATE_TYPE_ATTACHMENT: str = "attachment"


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Notes -----------------------------------------------------------------


class NoteCreatedPayload(_Payload):
    note_id: uuid.UUID
    entity_kind: str
    entity_id: uuid.UUID
    author_user_id: uuid.UUID
    body_preview: str


class NoteUpdatedPayload(_Payload):
    note_id: uuid.UUID
    body_preview_before: str
    body_preview_after: str


class NoteDeletedPayload(_Payload):
    note_id: uuid.UUID
    entity_kind: str
    entity_id: uuid.UUID


class NotePinnedPayload(_Payload):
    note_id: uuid.UUID


class NoteUnpinnedPayload(_Payload):
    note_id: uuid.UUID


# --- Attachments -----------------------------------------------------------


class AttachmentUploadedPayload(_Payload):
    attachment_id: uuid.UUID
    entity_kind: str
    entity_id: uuid.UUID
    filename: str
    mime_type: str
    byte_size: int


class AttachmentArchivedPayload(_Payload):
    attachment_id: uuid.UUID


TYPE_NOTE_CREATED = "platform.NoteCreated"
TYPE_NOTE_UPDATED = "platform.NoteUpdated"
TYPE_NOTE_DELETED = "platform.NoteDeleted"
TYPE_NOTE_PINNED = "platform.NotePinned"
TYPE_NOTE_UNPINNED = "platform.NoteUnpinned"
TYPE_ATTACHMENT_UPLOADED = "platform.AttachmentUploaded"
TYPE_ATTACHMENT_ARCHIVED = "platform.AttachmentArchived"


register_event(TYPE_NOTE_CREATED, NoteCreatedPayload)
register_event(TYPE_NOTE_UPDATED, NoteUpdatedPayload)
register_event(TYPE_NOTE_DELETED, NoteDeletedPayload)
register_event(TYPE_NOTE_PINNED, NotePinnedPayload)
register_event(TYPE_NOTE_UNPINNED, NoteUnpinnedPayload)
register_event(TYPE_ATTACHMENT_UPLOADED, AttachmentUploadedPayload)
register_event(TYPE_ATTACHMENT_ARCHIVED, AttachmentArchivedPayload)


def body_preview(body: str, limit: int = 100) -> str:
    """Return the first ``limit`` characters of ``body``.

    Used by the notes service before emitting an event so the payload
    never carries the full markdown body.
    """
    if body is None:
        return ""
    if len(body) <= limit:
        return body
    return body[:limit]
