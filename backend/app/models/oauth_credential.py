"""OAuth credential storage for third-party integrations (QBO — epic #312, #314).

One row per ``provider`` holds the live OAuth 2.0 tokens for a connected
external account. Currently only ``quickbooks`` is used: the row carries the
QuickBooks Online ``realm_id`` (company id) plus the access/refresh tokens and
their expiry timestamps (verified Phase-0 values: access 1 h, refresh 100-day
rolling — see ``docs/quickbooks_phase0_findings.md``).

Secret handling: the token columns are stored unencrypted, following the
established app precedent for secrets-at-rest (``email.smtp_password_secret``,
``camera.password_secret``, ``moonraker_api_key`` — all plain columns). They
are **never** serialized into API responses, events, or logs. (DB-level
encryption at rest would be a cross-cutting hardening item, tracked separately.)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

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
    # Secrets — never serialized/logged. See module docstring.
    access_token: Mapped[str] = mapped_column(Text(), nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text(), nullable=False)
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
