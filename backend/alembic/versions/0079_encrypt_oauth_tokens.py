"""Encrypt existing oauth_credential tokens at rest (epic #312 hardening).

The ``access_token`` / ``refresh_token`` columns are now Fernet-encrypted via
``app.core.crypto.EncryptedString`` (the column SQL type is unchanged — Text —
so this is a *data* migration, not a schema one). Any pre-existing rows held
plaintext; re-encrypt them in place so the ORM can decrypt them on read.

In practice there will usually be zero rows (QBO connections are short-lived
and rotate), in which case this migration is a no-op and ``SECRET_ENCRYPTION_KEY``
is not even required. When rows DO exist, the key must be configured — if it
isn't, the migration fails loudly rather than leaving half-encrypted data, and
the safe recovery is to disconnect/reconnect QuickBooks (which writes fresh,
correctly-encrypted tokens).

``downgrade`` reverses the transformation (decrypt back to plaintext) so the
chain stays reversible.

Revision ID: 0079_encrypt_oauth_tokens
Revises: 0078_oauth_credential
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0079_encrypt_oauth_tokens"
down_revision: str | None = "0078_oauth_credential"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SELECT = sa.text("SELECT id, access_token, refresh_token FROM oauth_credential")
_UPDATE = sa.text(
    "UPDATE oauth_credential SET access_token = :access, refresh_token = :refresh " "WHERE id = :id"
)


def _rewrite(transform) -> None:
    bind = op.get_bind()
    rows = bind.execute(_SELECT).fetchall()
    for row in rows:
        bind.execute(
            _UPDATE,
            {
                "id": row.id,
                "access": transform(row.access_token),
                "refresh": transform(row.refresh_token),
            },
        )


def upgrade() -> None:
    # Imported lazily so the migration module imports without cryptography or a
    # configured key when there's nothing to encrypt.
    from app.core.crypto import encrypt_secret

    _rewrite(encrypt_secret)


def downgrade() -> None:
    from app.core.crypto import decrypt_secret

    _rewrite(decrypt_secret)
