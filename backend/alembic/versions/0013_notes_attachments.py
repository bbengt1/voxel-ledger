"""notes + attachments tables (Phase 2.6)

Creates the polymorphic ``note`` and ``attachment`` tables and inserts a
default row for the ``attachments.storage_root`` setting if one does
not already exist. Both tables use polymorphic ``(entity_kind,
entity_id)`` refs — no FK on ``entity_id`` because it points across
multiple catalog tables, just like ``product_bom_item.component_id``.

Down-revision lineage: this migration chains after ``0011_product_bom``.
The parallel #41 (custom fields) takes ``0012`` — the merge-time rebase
will adjust this down_revision to follow whichever lands first.

Revision ID: 0013_notes_attachments
Revises: 0011_product_bom
Create Date: 2026-05-14 00:00:03.000000
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013_notes_attachments"
down_revision: str | None = "0011_product_bom"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STORAGE_ROOT_KEY = "attachments.storage_root"
_STORAGE_ROOT_DEFAULT = "/srv/3d-print-sales/data/attachments"


def upgrade() -> None:
    op.create_table(
        "note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "author_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_note_entity_pinned_created",
        "note",
        ["entity_kind", "entity_id", "is_pinned", "created_at"],
    )

    op.create_table(
        "attachment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_attachment_entity_archived_created",
        "attachment",
        ["entity_kind", "entity_id", "is_archived", "created_at"],
    )

    # Seed the storage_root setting if it isn't already present. Use a
    # one-shot INSERT guarded by NOT EXISTS so re-running the migration
    # against a partially-seeded DB stays idempotent.
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT 1 FROM setting WHERE key = :k"),
        {"k": _STORAGE_ROOT_KEY},
    ).scalar()
    if not existing:
        # Bind the value via a typed parameter so SQLAlchemy's JSON
        # adapter handles the dialect-specific serialization (text for
        # SQLite, JSONB binary for Postgres).
        value_type = sa.JSON().with_variant(JSONB(), "postgresql")
        stmt = sa.text(
            "INSERT INTO setting (key, value, updated_at, updated_by_user_id) "
            "VALUES (:k, :v, CURRENT_TIMESTAMP, NULL)"
        ).bindparams(sa.bindparam("v", type_=value_type))
        bind.execute(
            stmt,
            {"k": _STORAGE_ROOT_KEY, "v": _STORAGE_ROOT_DEFAULT},
        )
        _ = json
        _ = uuid


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM setting WHERE key = :k"),
        {"k": _STORAGE_ROOT_KEY},
    )
    op.drop_index("ix_attachment_entity_archived_created", table_name="attachment")
    op.drop_table("attachment")
    op.drop_index("ix_note_entity_pinned_created", table_name="note")
    op.drop_table("note")
