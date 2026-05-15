"""printer + camera tables (Phase 5.1, #77)

Creates the ``printer`` and ``camera`` tables plus the
``printer_type`` and ``camera_kind`` PG enums and a partial unique
index over ``(slug) WHERE is_archived = false``.

Per ops convention (see #49), enums are NOT pre-created. They are
referenced via a column with ``sa.Enum(*VALUES, name=...)`` and
``op.create_table`` creates the PG types through its dialect hook. On
SQLite the same construct renders as ``VARCHAR + CHECK``.

Booleans use ``sa.false()`` / ``sa.true()`` for ``server_default`` —
never integer literals — because Postgres rejects them on Boolean
columns.

Revision ID: 0022_printers_cameras
Revises: 0021_divisions_budgets
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_printers_cameras"
down_revision: str | None = "0021_divisions_budgets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRINTER_TYPE_VALUES = (
    "prusa_mk4",
    "prusa_mk3s",
    "bambu_x1c",
    "bambu_a1",
    "voron_v2_4",
    "other",
)

CAMERA_KIND_VALUES = (
    "wyze",
    "rtsp",
    "go2rtc",
    "other",
)


def upgrade() -> None:
    printer_type_enum = sa.Enum(*PRINTER_TYPE_VALUES, name="printer_type")
    camera_kind_enum = sa.Enum(*CAMERA_KIND_VALUES, name="camera_kind")

    op.create_table(
        "printer",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("printer_type", printer_type_enum, nullable=False),
        sa.Column("moonraker_url", sa.Text(), nullable=True),
        sa.Column("moonraker_api_key", sa.Text(), nullable=True),
        sa.Column("power_draw_watts", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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

    op.create_index(
        "ux_printer_slug_active",
        "printer",
        ["slug"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )

    op.create_table(
        "camera",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "printer_id",
            sa.Uuid(),
            sa.ForeignKey("printer.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("kind", camera_kind_enum, nullable=False),
        sa.Column("snapshot_url", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("password_secret", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
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


def downgrade() -> None:
    op.drop_table("camera")
    op.drop_index("ux_printer_slug_active", table_name="printer")
    op.drop_table("printer")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*CAMERA_KIND_VALUES, name="camera_kind").drop(bind, checkfirst=True)
        sa.Enum(*PRINTER_TYPE_VALUES, name="printer_type").drop(bind, checkfirst=True)
