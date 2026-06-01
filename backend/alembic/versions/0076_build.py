"""Build / assembly: build table + build_state enum + tx.linked_build_id (#267 Phase 5a).

A Build assembles a Product from its Parts + Supplies. The ``build`` table
holds the assembly run (draft → completed/cancelled) with an assembly-labor
field and a cost snapshot. ``inventory_transaction.linked_build_id`` groups
the consume-parts/supplies + credit-product rows a Build emits.

Revision ID: 0076_build
Revises: 0075_job_part
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.models.build import BUILD_STATE_VALUES

revision: str = "0076_build"
down_revision: str | None = "0075_job_part"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "build",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("build_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(*BUILD_STATE_VALUES, name="build_state"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "assembly_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "location_id",
            sa.Uuid(),
            sa.ForeignKey("inventory_location.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("unit_cost_cached", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("total_cost_cached", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
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
        sa.CheckConstraint("quantity > 0", name="ck_build_quantity_positive"),
        sa.CheckConstraint(
            "assembly_minutes >= 0", name="ck_build_assembly_minutes_nonneg"
        ),
    )
    op.create_index("ix_build_state_created", "build", ["state", "created_at"])
    op.create_index("ix_build_product_state", "build", ["product_id", "state"])

    op.add_column(
        "inventory_transaction",
        sa.Column("linked_build_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inventory_transaction", "linked_build_id")
    op.drop_index("ix_build_product_state", table_name="build")
    op.drop_index("ix_build_state_created", table_name="build")
    op.drop_table("build")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BUILD_STATE_VALUES, name="build_state").drop(bind, checkfirst=True)
