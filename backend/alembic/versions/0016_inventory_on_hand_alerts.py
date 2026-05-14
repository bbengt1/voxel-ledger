"""inventory_on_hand + low-stock thresholds (Phase 3.3, #52)

Creates the ``inventory_on_hand`` per-(entity, location) running-balance
table (maintained by the new ``inventory_on_hand`` projection), adds
``low_stock_threshold*`` columns to ``material`` / ``supply`` /
``product``, backfills existing on-hand quantities from
``material.on_hand_grams`` and ``supply.on_hand`` into the new table,
then drops those two columns.

Backfill destination
--------------------
For each row with a positive on-hand quantity, we insert one
``inventory_on_hand`` row at a default location:

1. ``inventory.default_receiving_location_id`` setting, if set.
2. Lowest-code active ``workshop`` location.
3. Otherwise — fail the migration. The operator must configure a
   destination before upgrading.

This is a **one-time data move**, not a re-projection. No events are
emitted. The inventory event log doesn't know about pre-#52 on-hand
state; the backfill simply preserves the cached number into the new
storage shape.

Downgrade
---------
Re-adds the dropped columns as nullable Numeric(18, 6); **on-hand data
is lost** since the columns reappear empty. Operators who need to roll
back should snapshot the database first.

Revision ID: 0016_inventory_on_hand_alerts
Revises: 0015_inventory_transactions
Create Date: 2026-05-14 00:00:06.000000
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_inventory_on_hand_alerts"
down_revision: str | None = "0015_inventory_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVENTORY_ENTITY_KIND_VALUES = ("material", "supply", "product")


def _resolve_default_location_id(bind) -> uuid.UUID | None:
    """Mirror ``inventory.default_receiving_location_id`` resolution.

    Read the setting, then fall back to lowest-code active workshop.
    Returns ``None`` when no candidate exists; the caller decides whether
    that's fatal (it is only fatal if there's actually data to backfill).
    """
    # 1. setting
    raw = bind.execute(
        sa.text("SELECT value FROM setting WHERE key = :k"),
        {"k": "inventory.default_receiving_location_id"},
    ).scalar_one_or_none()
    if raw is not None:
        try:
            # Setting values are stored as JSON-encoded scalars.
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, str):
                candidate = uuid.UUID(parsed)
                # Validate it's still active.
                row = bind.execute(
                    sa.text(
                        "SELECT id FROM inventory_location "
                        "WHERE id = :id AND is_archived = :archived"
                    ),
                    {"id": str(candidate), "archived": False},
                ).first()
                if row is not None:
                    return candidate
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    # 2. fallback: lowest-code active workshop
    row = bind.execute(
        sa.text(
            "SELECT id FROM inventory_location "
            "WHERE kind = 'workshop' AND is_archived = :archived "
            "ORDER BY code ASC LIMIT 1"
        ),
        {"archived": False},
    ).first()
    if row is not None:
        return uuid.UUID(str(row[0]))
    return None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # --- 1. Create inventory_on_hand table ---
    # The ``inventory_entity_kind`` PG enum was created by 0015 alongside
    # ``inventory_transaction``. We need to reference it on a column WITHOUT
    # triggering op.create_table's auto-create hook, which fires regardless
    # of ``create_type=False`` on a generic ``sa.Enum`` (see #49 / #55).
    #
    # On PG: use the dialect-specific ``postgresql.ENUM`` with
    # ``create_type=False``. The dialect class honors the flag in its
    # ``create()`` short-circuit, so the hook still fires but no-ops.
    # On SQLite: a plain ``sa.Enum`` renders as VARCHAR + CHECK and there
    # is no "already exists" problem to worry about.
    if is_pg:
        entity_kind_col_type = postgresql.ENUM(
            *INVENTORY_ENTITY_KIND_VALUES,
            name="inventory_entity_kind",
            create_type=False,
        )
    else:
        entity_kind_col_type = sa.Enum(
            *INVENTORY_ENTITY_KIND_VALUES,
            name="inventory_entity_kind",
        )

    entity_kind_col = sa.Column(
        "entity_kind",
        entity_kind_col_type,
        nullable=False,
    )
    op.create_table(
        "inventory_on_hand",
        sa.Column("id", sa.Uuid(), primary_key=True),
        entity_kind_col,
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "location_id",
            sa.Uuid(),
            sa.ForeignKey("inventory_location.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("on_hand", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "entity_kind",
            "entity_id",
            "location_id",
            name="uq_inventory_on_hand_entity_location",
        ),
    )
    op.create_index(
        "ix_inventory_on_hand_entity",
        "inventory_on_hand",
        ["entity_kind", "entity_id"],
    )
    op.create_index(
        "ix_inventory_on_hand_location",
        "inventory_on_hand",
        ["location_id"],
    )

    # --- 2. Add low-stock threshold columns ---
    op.add_column(
        "material",
        sa.Column("low_stock_threshold_grams", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "supply",
        sa.Column("low_stock_threshold", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "product",
        sa.Column("low_stock_threshold", sa.Numeric(18, 6), nullable=True),
    )

    # --- 3. Backfill from existing on-hand columns ---
    material_rows = list(
        bind.execute(sa.text("SELECT id, on_hand_grams FROM material WHERE on_hand_grams > 0"))
    )
    supply_rows = list(bind.execute(sa.text("SELECT id, on_hand FROM supply WHERE on_hand > 0")))

    if material_rows or supply_rows:
        default_loc = _resolve_default_location_id(bind)
        if default_loc is None:
            raise RuntimeError(
                "0016_inventory_on_hand_alerts: cannot backfill on-hand data — "
                "no default location. Configure "
                "inventory.default_receiving_location_id or create at least one "
                "active workshop location before upgrading."
            )
        for row in material_rows:
            entity_id, qty = row[0], row[1]
            bind.execute(
                sa.text(
                    "INSERT INTO inventory_on_hand "
                    "(id, entity_kind, entity_id, location_id, on_hand, updated_at) "
                    "VALUES (:id, 'material', :eid, :loc, :q, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "eid": str(entity_id),
                    "loc": str(default_loc),
                    "q": str(Decimal(qty)),
                },
            )
        for row in supply_rows:
            entity_id, qty = row[0], row[1]
            bind.execute(
                sa.text(
                    "INSERT INTO inventory_on_hand "
                    "(id, entity_kind, entity_id, location_id, on_hand, updated_at) "
                    "VALUES (:id, 'supply', :eid, :loc, :q, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "eid": str(entity_id),
                    "loc": str(default_loc),
                    "q": str(Decimal(qty)),
                },
            )

    # --- 4. Drop the old on-hand columns ---
    op.drop_column("material", "on_hand_grams")
    op.drop_column("supply", "on_hand")


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.add_column(
        "material",
        sa.Column("on_hand_grams", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "supply",
        sa.Column("on_hand", sa.Numeric(18, 6), nullable=True),
    )

    op.drop_column("product", "low_stock_threshold")
    op.drop_column("supply", "low_stock_threshold")
    op.drop_column("material", "low_stock_threshold_grams")

    op.drop_index("ix_inventory_on_hand_location", table_name="inventory_on_hand")
    op.drop_index("ix_inventory_on_hand_entity", table_name="inventory_on_hand")
    op.drop_table("inventory_on_hand")

    # The inventory_entity_kind enum is shared with inventory_transaction
    # (created in 0015) — do NOT drop it here. 0015's downgrade owns it.
    _ = is_pg
