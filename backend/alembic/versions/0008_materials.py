"""materials & material_receipts catalog tables

Creates the catalog ``material`` table and the ``material_receipt``
sub-resource table that drives weighted-average cost-per-gram via the
``material_cost`` projection (Phase 2.1, #37).

``material.current_cost_per_gram`` and ``material.on_hand_grams`` are
read-side caches owned by the projection — they are not mutated by
service code. The unique constraint on ``(name, brand, color)`` is
partial: ``WHERE is_archived = false``, so archived rows can coexist
with a fresh same-named entry. SQLite supports partial indexes too
(only Postgres-shaped syntax differs).

Revision ID: 0008_materials
Revises: 0007_settings
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_materials"
down_revision: str | None = "0007_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("material_type", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("density_g_per_cm3", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "current_cost_per_gram",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "on_hand_grams",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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

    # Partial unique index — only enforces uniqueness across active
    # (non-archived) rows. Works on both Postgres and SQLite (which has
    # supported partial indexes since 3.8.0).
    op.create_index(
        "ux_material_name_brand_color_active",
        "material",
        ["name", "brand", "color"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )

    op.create_table(
        "material_receipt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("material.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("grams", sa.Numeric(18, 6), nullable=False),
        sa.Column("total_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_cost_at_receipt", sa.Numeric(18, 6), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("grams > 0", name="ck_material_receipt_grams_positive"),
        sa.CheckConstraint("total_cost >= 0", name="ck_material_receipt_total_cost_non_negative"),
    )

    op.create_index(
        "ix_material_receipt_material_received_at",
        "material_receipt",
        ["material_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_material_receipt_material_received_at", table_name="material_receipt")
    op.drop_table("material_receipt")
    op.drop_index("ux_material_name_brand_color_active", table_name="material")
    op.drop_table("material")
