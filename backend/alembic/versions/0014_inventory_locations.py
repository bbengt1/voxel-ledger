"""inventory_location table (Phase 3.1, #50)

Creates the ``inventory_location`` table plus the ``inventory_location_kind``
PG enum and a partial unique index over ``(code) WHERE is_archived = false``.

Per ops convention (see #49), the enum is NOT pre-created. We reference
it on a column via ``sa.Enum(*VALUES, name=...)`` and let
``op.create_table`` create it through the dialect hook on PG. On SQLite
the same construct renders as ``VARCHAR + CHECK``.

Booleans use ``sa.false()`` for ``server_default`` — never integer
literals — because Postgres rejects them on Boolean columns.

Revision ID: 0014_inventory_locations
Revises: 0013_notes_attachments
Create Date: 2026-05-14 00:00:04.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_inventory_locations"
down_revision: str | None = "0013_notes_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVENTORY_LOCATION_KIND_VALUES = (
    "workshop",
    "finished_goods",
    "staging",
    "customer_pickup",
    "consignment",
    "virtual",
)


def upgrade() -> None:
    kind_enum = sa.Enum(*INVENTORY_LOCATION_KIND_VALUES, name="inventory_location_kind")

    op.create_table(
        "inventory_location",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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

    # Partial unique index: only active rows enforce code uniqueness.
    op.create_index(
        "ux_inventory_location_code_active",
        "inventory_location",
        ["code"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_inventory_location_code_active", table_name="inventory_location"
    )
    op.drop_table("inventory_location")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*INVENTORY_LOCATION_KIND_VALUES, name="inventory_location_kind").drop(
            bind, checkfirst=True
        )
