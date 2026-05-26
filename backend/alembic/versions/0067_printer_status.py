"""Operational status enum on ``printer``.

Adds ``status`` (``active`` / ``inactive`` / ``decommissioned``)
independent of ``is_archived``. ``is_archived`` keeps its existing
semantic (hidden from default lists); ``status`` describes the
operational state of an active row.

Revision ID: 0067_printer_status
Revises: 0066_supply_purchase_fields
Create Date: 2026-05-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067_printer_status"
down_revision: str | None = "0066_supply_purchase_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRINTER_STATUS_VALUES = ("active", "inactive", "decommissioned")


def upgrade() -> None:
    status_enum = sa.Enum(*PRINTER_STATUS_VALUES, name="printer_status")
    # ``add_column`` does NOT auto-create the enum type on Postgres
    # (only ``create_table`` does via the column hook). Create it
    # explicitly first; ``create_type=False`` on the column avoids a
    # duplicate create attempt.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        status_enum.create(bind, checkfirst=True)
    column_enum = sa.Enum(*PRINTER_STATUS_VALUES, name="printer_status", create_type=False)
    op.add_column(
        "printer",
        sa.Column(
            "status",
            column_enum,
            nullable=False,
            server_default="active",
        ),
    )


def downgrade() -> None:
    op.drop_column("printer", "status")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS printer_status")
