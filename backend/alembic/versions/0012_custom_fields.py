"""custom fields & form templates (Phase 2.5)

Creates the ``custom_field``, ``form_template``, and
``form_template_field`` tables plus their indexes; adds a
``custom_fields jsonb NOT NULL DEFAULT '{}'`` column to each of the four
catalog entity tables (material, supply, rate, product).

The ``custom_field_type`` PG ENUM is created here and dropped on the
downgrade. On SQLite the enum becomes a plain VARCHAR with a CHECK
constraint, courtesy of ``sa.Enum`` rendering.

Revision ID: 0012_custom_fields
Revises: 0011_product_bom
Create Date: 2026-05-14 00:00:03.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012_custom_fields"
down_revision: str | None = "0011_product_bom"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CUSTOM_FIELD_TYPE_VALUES = ("string", "number", "boolean", "date", "select")
ENTITY_TYPE_VALUES = ("material", "supply", "rate", "product")


def _jsonb_or_json(is_pg: bool) -> sa.types.TypeEngine:
    return JSONB() if is_pg else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # Create the field-type enum first so it can be referenced by name on
    # PG; on SQLite, sa.Enum renders as VARCHAR with CHECK.
    if is_pg:
        sa.Enum(*CUSTOM_FIELD_TYPE_VALUES, name="custom_field_type").create(bind, checkfirst=True)
        field_type_col = sa.Column(
            "field_type",
            sa.Enum(
                *CUSTOM_FIELD_TYPE_VALUES,
                name="custom_field_type",
                create_type=False,
            ),
            nullable=False,
        )
    else:
        field_type_col = sa.Column(
            "field_type",
            sa.String(length=16),
            sa.CheckConstraint(
                "field_type IN ('string','number','boolean','date','select')",
                name="ck_custom_field_field_type",
            ),
            nullable=False,
        )

    json_type = _jsonb_or_json(is_pg)

    op.create_table(
        "custom_field",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        field_type_col,
        sa.Column("options", json_type, nullable=True),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false") if is_pg else sa.text("0"),
        ),
        sa.Column("default_value", json_type, nullable=True),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false") if is_pg else sa.text("0"),
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
        sa.CheckConstraint(
            "entity_type IN ('material','supply','rate','product')",
            name="ck_custom_field_entity_type",
        ),
    )
    op.create_index(
        "ix_custom_field_entity_type",
        "custom_field",
        ["entity_type"],
    )
    op.create_index(
        "ux_custom_field_entity_type_key_active",
        "custom_field",
        ["entity_type", "key"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )

    op.create_table(
        "form_template",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_default_for_entity_type",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false") if is_pg else sa.text("0"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false") if is_pg else sa.text("0"),
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
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
        sa.CheckConstraint(
            "entity_type IN ('material','supply','rate','product')",
            name="ck_form_template_entity_type",
        ),
    )
    op.create_index(
        "ix_form_template_entity_type",
        "form_template",
        ["entity_type"],
    )
    op.create_index(
        "ux_form_template_default_per_entity_type",
        "form_template",
        ["entity_type"],
        unique=True,
        sqlite_where=sa.text("is_default_for_entity_type = 1"),
        postgresql_where=sa.text("is_default_for_entity_type = true"),
    )

    op.create_table(
        "form_template_field",
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("form_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "custom_field_id",
            sa.Uuid(),
            sa.ForeignKey("custom_field.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("template_id", "custom_field_id", name="pk_form_template_field"),
    )

    # Add ``custom_fields`` jsonb column to each of the four catalog
    # entity tables. ``'{}'::jsonb`` on PG, plain ``'{}'`` on SQLite —
    # the rendered type does the right thing because of the JSON variant.
    default_sql = sa.text("'{}'::jsonb") if is_pg else sa.text("'{}'")
    for table_name in ENTITY_TYPE_VALUES:
        op.add_column(
            table_name,
            sa.Column(
                "custom_fields",
                json_type,
                nullable=False,
                server_default=default_sql,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    for table_name in ENTITY_TYPE_VALUES:
        op.drop_column(table_name, "custom_fields")

    op.drop_table("form_template_field")

    op.drop_index(
        "ux_form_template_default_per_entity_type",
        table_name="form_template",
    )
    op.drop_index("ix_form_template_entity_type", table_name="form_template")
    op.drop_table("form_template")

    op.drop_index(
        "ux_custom_field_entity_type_key_active",
        table_name="custom_field",
    )
    op.drop_index("ix_custom_field_entity_type", table_name="custom_field")
    op.drop_table("custom_field")

    if is_pg:
        sa.Enum(*CUSTOM_FIELD_TYPE_VALUES, name="custom_field_type").drop(bind, checkfirst=True)
