"""Product assembly: ``part`` BOM kind + ``product.assembly_minutes`` (#267 Phase 3a).

Products become assemblies of parts + supplies. Adds ``part`` to the
``bom_component_kind`` enum (Postgres) and an ``assembly_minutes`` column
to ``product`` (labor to assemble one finished product, costed at the
labor rate). Legacy ``material`` / ``product`` BOM rows are untouched.

Revision ID: 0074_product_assembly
Revises: 0073_part
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0074_product_assembly"
down_revision: str | None = "0073_part"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("assembly_minutes", sa.Integer(), server_default="0", nullable=False),
    )
    # Add the new polymorphic kind. Native PG enum needs ALTER TYPE; on
    # SQLite the kind is a CHECK constraint recreated from metadata, so this
    # is a no-op there. PG 12+ allows ADD VALUE inside a transaction.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE bom_component_kind ADD VALUE IF NOT EXISTS 'part'")


def downgrade() -> None:
    op.drop_column("product", "assembly_minutes")
    # Postgres can't easily drop an enum value; leaving 'part' in the enum
    # on downgrade is harmless (no rows reference it after the column drop).
