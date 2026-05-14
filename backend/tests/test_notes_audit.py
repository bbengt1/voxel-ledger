"""Notes events surface to audit + body preview is truncated."""

from __future__ import annotations

from app.events.types import notes_attachments as notes_events
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary


def test_body_is_never_whitelisted() -> None:
    """The whitelist must not contain ``body`` — only the 100-char preview."""
    excerpt = compute_excerpt(
        notes_events.TYPE_NOTE_CREATED,
        {
            "note_id": "n",
            "entity_kind": "material",
            "entity_id": "e",
            "author_user_id": "u",
            "body_preview": "the first hundred chars",
            "body": "FULL BODY MUST NEVER LEAK",
        },
    )
    assert excerpt is not None
    assert "body" not in excerpt
    assert excerpt["body_preview"] == "the first hundred chars"


def test_body_preview_truncates_to_100_chars() -> None:
    long = "x" * 250
    assert notes_events.body_preview(long) == "x" * 100
    assert notes_events.body_preview("short") == "short"
    assert notes_events.body_preview("") == ""


def test_note_updated_excerpt_holds_only_previews() -> None:
    excerpt = compute_excerpt(
        notes_events.TYPE_NOTE_UPDATED,
        {
            "note_id": "n",
            "body_preview_before": "before",
            "body_preview_after": "after",
            # If this somehow appeared in the payload, the excerpt must
            # still not surface it.
            "body": "FULL BODY",
        },
    )
    assert excerpt == {"body_preview_before": "before", "body_preview_after": "after"}


def test_attachment_uploaded_excerpt_omits_storage_path() -> None:
    """``storage_path`` is private — never in excerpts."""
    excerpt = compute_excerpt(
        notes_events.TYPE_ATTACHMENT_UPLOADED,
        {
            "attachment_id": "a",
            "entity_kind": "material",
            "entity_id": "e",
            "filename": "pic.png",
            "mime_type": "image/png",
            "byte_size": 42,
            "storage_path": "2026/05/some.png",
        },
    )
    assert excerpt is not None
    assert "storage_path" not in excerpt
    assert excerpt["filename"] == "pic.png"


def test_summary_renders_for_all_seven_events() -> None:
    for event_type, payload in [
        (
            notes_events.TYPE_NOTE_CREATED,
            {
                "note_id": "n",
                "entity_kind": "material",
                "entity_id": "e",
                "author_user_id": "u",
                "body_preview": "hello",
            },
        ),
        (
            notes_events.TYPE_NOTE_UPDATED,
            {
                "note_id": "n",
                "body_preview_before": "a",
                "body_preview_after": "b",
            },
        ),
        (
            notes_events.TYPE_NOTE_DELETED,
            {"note_id": "n", "entity_kind": "material", "entity_id": "e"},
        ),
        (notes_events.TYPE_NOTE_PINNED, {"note_id": "n"}),
        (notes_events.TYPE_NOTE_UNPINNED, {"note_id": "n"}),
        (
            notes_events.TYPE_ATTACHMENT_UPLOADED,
            {
                "attachment_id": "a",
                "entity_kind": "material",
                "entity_id": "e",
                "filename": "x.pdf",
                "mime_type": "application/pdf",
                "byte_size": 10,
            },
        ),
        (notes_events.TYPE_ATTACHMENT_ARCHIVED, {"attachment_id": "a"}),
    ]:
        out = render_summary(
            event_type,
            payload,
            actor_label="ada@example.com",
            aggregate_type="note",
            aggregate_id="x",
        )
        # The generic fall-through would contain "did <event_type>" — we
        # explicitly registered a formatter, so make sure it took.
        assert "did " + event_type not in out
        assert "ada@example.com" in out
