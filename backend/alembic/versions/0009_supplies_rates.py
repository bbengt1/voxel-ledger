"""supplies & rates catalog tables

Creates the ``supply`` and ``rate`` catalog tables (Phase 2.2, #38).

Supplies are unit-cost consumables — no receipts sub-resource, since
``unit_cost`` is set directly on create/update. ``on_hand`` is a
read-side cache the Phase 3 inventory transactions will own.

Rates are typed by an enum ``rate_kind`` (labor/machine/overhead). The
partial unique index ``ux_rate_default_per_kind`` enforces at most one
default per kind at the DB level so the service-layer "flip" sequence
in ``set_default`` is backstopped.

Like materials, both tables use partial unique indexes:
  - supply: ``(name, vendor) WHERE is_archived = false``
  - rate: ``(kind) WHERE is_default_for_kind = true``

SQLite (used for unit tests) supports partial indexes since 3.8.0 and
falls back to a CHECK constraint for the enum, matching the
``0002_auth.py`` pattern.

Revision ID: 0009_supplies_rates
Revises: 0008_materials
Create Date: 2026-05-14 00:00:01.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_supplies_rates"
down_revision: str | None = "0008_materials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RATE_KIND_VALUES = ("labor", "machine", "overhead")


def upgrade() -> None:
    # Let SQLAlchemy auto-create the `rate_kind` enum via op.create_table
    # on PG; SQLite renders it as a CHECK constraint. Matches the
    # ``role`` enum pattern from 0002_auth.py.
    rate_kind_enum = sa.Enum(*RATE_KIND_VALUES, name="rate_kind")

    op.create_table(
        "supply",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column(
            "on_hand",
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

    # Partial unique index: only enforces uniqueness across active rows.
    op.create_index(
        "ux_supply_name_vendor_active",
        "supply",
        ["name", "vendor"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )

    op.create_table(
        "rate",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", rate_kind_enum, nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        # No FK yet — Phase 5's ``printer`` table doesn't exist. The
        # column carries the eventual intent (machine-rate scoping).
        sa.Column("applies_to_printer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_default_for_kind",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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

    # At most one default per kind, enforced at the DB level. Backstops
    # the service-layer flip in ``rates.set_default``.
    op.create_index(
        "ux_rate_default_per_kind",
        "rate",
        ["kind"],
        unique=True,
        sqlite_where=sa.text("is_default_for_kind = 1"),
        postgresql_where=sa.text("is_default_for_kind = true"),
    )


def downgrade() -> None:
    op.drop_index("ux_rate_default_per_kind", table_name="rate")
    op.drop_table("rate")
    op.drop_index("ux_supply_name_vendor_active", table_name="supply")
    op.drop_table("supply")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*RATE_KIND_VALUES, name="rate_kind").drop(bind, checkfirst=True)
