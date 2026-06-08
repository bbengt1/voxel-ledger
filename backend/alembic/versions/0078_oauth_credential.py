"""oauth_credential: encrypted-at-app-layer OAuth token storage for QBO (#314).

One row per provider holds the live OAuth 2.0 tokens for a connected external
account (QuickBooks Online). Part of epic #312.

Revision ID: 0078_oauth_credential
Revises: 0077_job_description
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.models.oauth_credential import OAUTH_PROVIDER_VALUES

revision: str = "0078_oauth_credential"
down_revision: str | None = "0077_job_description"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_credential",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "provider",
            sa.Enum(*OAUTH_PROVIDER_VALUES, name="oauth_provider"),
            nullable=False,
        ),
        sa.Column("realm_id", sa.String(length=64), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("provider", name="ux_oauth_credential_provider"),
    )


def downgrade() -> None:
    op.drop_table("oauth_credential")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*OAUTH_PROVIDER_VALUES, name="oauth_provider").drop(bind, checkfirst=True)
