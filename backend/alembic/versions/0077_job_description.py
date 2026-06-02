"""Add a free-text ``description`` column to ``job``.

Replaces the old frontend hack of stuffing a "Customer: …" free-text line
into ``notes``. The new-job form's free-text box now writes a first-class
``description`` that the jobs list can display.

Revision ID: 0077_job_description
Revises: 0076_build
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077_job_description"
down_revision: str | None = "0076_build"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "description")
