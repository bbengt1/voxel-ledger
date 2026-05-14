"""reference_sequence allocator table

Creates the ``reference_sequence`` table that backs the race-safe
``{PREFIX}-{YYYY}-{NNNN}`` allocator. See v1 issue #243 for the incident
that motivated moving away from COUNT-based numbering. The allocator
uses ``INSERT ... ON CONFLICT (prefix, year) DO UPDATE SET last_value =
reference_sequence.last_value + 1 RETURNING last_value`` — one atomic
round-trip, row-locked, with no read-modify-write window.

Revision ID: 0005_reference_sequence
Revises: 0003_event_log
Create Date: 2026-05-14 00:00:00.000000

Note: revision 0004 is reserved for the projection_cursor table being
landed in parallel by issue #22. Whichever PR merges second will rebase
its ``down_revision`` to chain after the other; alembic supports either
order as long as the resulting graph is linear.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reference_sequence"
down_revision: str | None = "0003_event_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_sequence",
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column(
            "last_value",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("prefix", "year", name="pk_reference_sequence"),
    )


def downgrade() -> None:
    op.drop_table("reference_sequence")
