"""approval_request table (Phase 4.4, #67)

Creates the generic approval-queue table plus the ``approval_state`` PG
enum and four supporting indexes. The enum is NOT pre-created — we
reference it via ``sa.Enum(*VALUES, name=...)`` on the column and let
``op.create_table`` create it on PG (#49). On SQLite it renders as
``VARCHAR + CHECK``.

``payload`` is JSON on SQLite, JSONB on PG.

Revision ID: 0020_approvals
Revises: 0018_journal_entries
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020_approvals"
down_revision: str | None = "0018_journal_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPROVAL_STATE_VALUES = (
    "pending",
    "approved",
    "rejected",
    "cancelled",
)


def upgrade() -> None:
    approval_state_enum = sa.Enum(*APPROVAL_STATE_VALUES, name="approval_state")
    payload_type = sa.JSON().with_variant(JSONB(), "postgresql")

    op.create_table(
        "approval_request",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_type", sa.String(length=128), nullable=False),
        sa.Column("subject_kind", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "state",
            approval_state_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "decided_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("threshold_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_approval_request_state_requested_at",
        "approval_request",
        ["state", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_approval_request_type_state",
        "approval_request",
        ["request_type", "state"],
    )
    op.create_index(
        "ix_approval_request_subject",
        "approval_request",
        ["subject_kind", "subject_id"],
    )
    op.create_index(
        "ix_approval_request_requester",
        "approval_request",
        ["requested_by_user_id", sa.text("requested_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_request_requester", table_name="approval_request")
    op.drop_index("ix_approval_request_subject", table_name="approval_request")
    op.drop_index("ix_approval_request_type_state", table_name="approval_request")
    op.drop_index("ix_approval_request_state_requested_at", table_name="approval_request")
    op.drop_table("approval_request")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*APPROVAL_STATE_VALUES, name="approval_state").drop(bind, checkfirst=True)
