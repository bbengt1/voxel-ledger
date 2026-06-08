"""OAuth credential storage for third-party integrations (QBO — epic #312, #314).

One row per ``provider`` holds the live OAuth 2.0 tokens for a connected
external account. Currently only ``quickbooks`` is used: the row carries the
QuickBooks Online ``realm_id`` (company id) plus the access/refresh tokens and
their expiry timestamps (verified Phase-0 values: access 1 h, refresh 100-day
rolling — see ``docs/quickbooks_phase0_findings.md``).

Secret handling: the access/refresh token columns are **encrypted at rest**
via :class:`app.core.crypto.EncryptedString` (Fernet) — the ciphertext is all
that ever touches the database, and the ORM transparently decrypts on read so
``app/services/quickbooks/oauth.py`` keeps working with plaintext ``str``
values. They are additionally **never** serialized into API responses, events,
or logs. See ``docs/secrets-at-rest.md`` for the encryption standard; this is
the first table to adopt it (the older ``email.smtp_password_secret``,
``camera.password_secret``, ``moonraker_api_key`` plaintext columns are
candidates to migrate next).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.db import Base


class OAuthProvider(enum.StrEnum):
    QUICKBOOKS = "quickbooks"


OAUTH_PROVIDER_VALUES: tuple[str, ...] = tuple(m.value for m in OAuthProvider)

OAUTH_PROVIDER_ENUM = SAEnum(
    *OAUTH_PROVIDER_VALUES,
    name="oauth_provider",
    create_type=False,
)


class OAuthCredential(Base):
    """Live OAuth tokens for one connected external provider (singleton/provider)."""

    __tablename__ = "oauth_credential"
    __table_args__ = (UniqueConstraint("provider", name="ux_oauth_credential_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(OAUTH_PROVIDER_ENUM, nullable=False)
    # QuickBooks company id; present in the path of every QBO API call.
    realm_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Secrets — encrypted at rest (Fernet) and never serialized/logged. The
    # EncryptedString type stores ciphertext but presents plaintext to the ORM.
    # See module docstring + app/core/crypto.py.
    access_token: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    refresh_token: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    refresh_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scope: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
