"""Jobs produce Parts: job.part_id + nullable product_id + part inventory kind (#267 Phase 4a).

A job now targets a Part. ``job.part_id`` is added (FK→part), ``job.product_id``
becomes nullable (legacy product-jobs, backfilled to parts in Phase 7), and
``part`` is added to the ``inventory_entity_kind`` enum so completion can
credit part stock.

Revision ID: 0075_job_part
Revises: 0074_product_assembly
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075_job_part"
down_revision: str | None = "0074_product_assembly"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("part_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_job_part_id", "job", "part", ["part_id"], ["id"], ondelete="RESTRICT")
    op.alter_column("job", "product_id", existing_type=sa.Uuid(), nullable=True)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE inventory_entity_kind ADD VALUE IF NOT EXISTS 'part'")


def downgrade() -> None:
    op.drop_constraint("fk_job_part_id", "job", type_="foreignkey")
    op.drop_column("job", "part_id")
    op.alter_column("job", "product_id", existing_type=sa.Uuid(), nullable=False)
    # Leaving 'part' in the inventory_entity_kind enum on downgrade is
    # harmless (no rows reference it after part_id is dropped).
