"""email_message table + email_kind / email_state enums (Phase 7.7, #115).

Creates the ``email_message`` outbound-delivery-log table along with the
two PG enums (``email_kind``, ``email_state``). Adds a unique partial
index on ``(kind, subject_kind, subject_id)`` for replay-safe idempotency
of dispatcher-driven enqueues (``QuoteSent`` / ``InvoiceIssued`` /
``RecurringInvoiceMaterialized``).

Per agents.md gotcha #1 the enums are NOT pre-created — ``op.create_table``
auto-creates them via the columns' dialect hook.

Revision ID: 0039_email
Revises: 0035_invoices
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_email"
down_revision: str | None = "0035_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMAIL_KIND_VALUES = (
    "quote",
    "invoice",
    "statement",
    "recurring_invoice",
    "password_reset",
    "generic",
)

EMAIL_STATE_VALUES = (
    "queued",
    "sending",
    "sent",
    "failed",
    "bounced",
)


def upgrade() -> None:
    email_kind_enum = sa.Enum(*EMAIL_KIND_VALUES, name="email_kind")
    email_state_enum = sa.Enum(*EMAIL_STATE_VALUES, name="email_state")

    op.create_table(
        "email_message",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", email_kind_enum, nullable=False),
        sa.Column("subject_kind", sa.String(length=64), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("to_address", sa.String(length=320), nullable=False),
        sa.Column("from_address", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_html_storage_key", sa.Text(), nullable=False),
        sa.Column("attachments_json", sa.JSON(), nullable=True),
        sa.Column(
            "state",
            email_state_enum,
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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

    op.create_index("ix_email_message_state", "email_message", ["state"])
    op.create_index("ix_email_message_kind", "email_message", ["kind"])
    op.create_index("ix_email_message_subject", "email_message", ["subject_kind", "subject_id"])
    op.create_index("ix_email_message_next_retry_at", "email_message", ["next_retry_at"])
    op.create_index("ix_email_message_created_at", "email_message", ["created_at"])

    # Idempotency: dispatcher re-emits replay-safe because this partial
    # unique index prevents double-queuing for the same upstream subject.
    # NULL subject_id rows (manual sends, password resets) bypass the
    # constraint entirely.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_email_message_kind_subject",
            "email_message",
            ["kind", "subject_kind", "subject_id"],
            unique=True,
            postgresql_where=sa.text("subject_id IS NOT NULL"),
        )
    else:
        # SQLite supports partial indexes via WHERE clause too.
        op.create_index(
            "uq_email_message_kind_subject",
            "email_message",
            ["kind", "subject_kind", "subject_id"],
            unique=True,
            sqlite_where=sa.text("subject_id IS NOT NULL"),
        )


def downgrade() -> None:
    op.drop_index("uq_email_message_kind_subject", table_name="email_message")
    op.drop_index("ix_email_message_created_at", table_name="email_message")
    op.drop_index("ix_email_message_next_retry_at", table_name="email_message")
    op.drop_index("ix_email_message_subject", table_name="email_message")
    op.drop_index("ix_email_message_kind", table_name="email_message")
    op.drop_index("ix_email_message_state", table_name="email_message")
    op.drop_table("email_message")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*EMAIL_STATE_VALUES, name="email_state").drop(bind, checkfirst=True)
        sa.Enum(*EMAIL_KIND_VALUES, name="email_kind").drop(bind, checkfirst=True)
