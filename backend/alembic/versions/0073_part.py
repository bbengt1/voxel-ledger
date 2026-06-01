"""Add ``part`` table (assembly-line epic #267, Phase 1).

A part is a printed unit (made of materials) that products are assembled
from. Carries its print recipe (minutes, setup, parts-per-run, per-material
grams, eligible printers) and a reserved ``unit_cost_cached`` for the
Phase 2 cost rollup. No wiring to products/jobs/inventory in this phase.

Revision ID: 0073_part
Revises: 0072_user_preference
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073_part"
down_revision: str | None = "0072_user_preference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "part",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("print_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("setup_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parts_per_run", sa.Integer(), server_default="1", nullable=False),
        sa.Column("print_grams_by_material", _JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("assigned_printer_ids", _JSON, server_default=sa.text("'[]'"), nullable=False),
        sa.Column("unit_cost_cached", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("custom_fields", _JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", name="uq_part_sku"),
    )


def downgrade() -> None:
    op.drop_table("part")
