"""projection cursor + test-only projection read model

Adds the ``projection_cursor`` table (used during replay only) and the
``projection_test_event`` read-model table (test-only, fed by
``app.projections.test_event_projection``).

Revision ID: 0004_projection_cursor
Revises: 0003_event_log
Create Date: 2026-05-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_projection_cursor"
down_revision: str | None = "0003_event_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projection_cursor",
        sa.Column("handler_name", sa.String(length=255), primary_key=True),
        sa.Column(
            "last_position",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "projection_test_event",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("projection_test_event")
    op.drop_table("projection_cursor")
