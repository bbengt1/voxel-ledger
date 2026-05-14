"""operational settings table

Creates the ``setting`` table that backs the runtime-editable, typed
key/value operational settings store (Phase 1.5). Distinct from the
deployment-time, env-driven ``app.core.settings.Settings``: that one is
read-only at boot, this one is mutated by the owner via the API.

Revision ID: 0007_settings
Revises: 0006_audit_log
Create Date: 2026-05-14 00:00:00.000000

Note on the alembic graph: issue #24 (audit log, revision 0006) was
landed in parallel and merged first; this migration was rebased onto
0006 at merge time to keep the alembic graph linear.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007_settings"
down_revision: str | None = "0006_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "setting",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column(
            "value",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
            name="fk_setting_updated_by_user_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("setting")
