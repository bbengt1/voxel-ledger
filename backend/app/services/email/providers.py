"""Email provider abstraction (Phase 7.7, #115).

A provider knows how to actually deliver one rendered email — over SMTP,
to a file, or to a vendor API. The service layer (see ``service.py``)
owns persistence + retry; providers are pure "given these bytes, send
them" units. That keeps the swap surface tiny.

Three implementations land in this phase:

* :class:`StaticFileProvider` writes the message + attachments to disk
  under ``{email.storage_root}/static_outbox/`` and returns a synthetic
  message id. The default for local dev and tests — never raises on the
  happy path, never depends on network.
* :class:`SmtpProvider` uses ``aiosmtplib`` to talk to the configured
  SMTP relay. Reads ``email.smtp_*`` settings via the constructor so the
  factory keeps the settings-reading concern out of the provider.
* :class:`SesProvider` is a stub. SES integration is OUT OF SCOPE for
  this phase; the class raises ``NotImplementedError`` so a misconfigured
  factory blows up loudly rather than silently dropping mail.

Factory: :func:`get_email_provider` reads ``email.provider`` (and falls
back to ``static_file`` when no SMTP host is set). The result is one
instance — providers are stateless so a singleton would work too, but
constructing per-call keeps the lifetime story simple.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


@dataclass
class Attachment:
    """One outbound attachment: a filename + raw bytes."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class ProviderResult:
    """The outcome of one ``send`` call."""

    provider_message_id: str
    status: str = "sent"
    raw_response: dict[str, Any] = field(default_factory=dict)


class EmailProvider(Protocol):
    """The contract every backend implementation satisfies."""

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body_html: str,
        body_text: str | None,
        attachments: list[Attachment],
        from_address: str,
    ) -> ProviderResult: ...


# ---------------------------------------------------------------------------
# StaticFileProvider
# ---------------------------------------------------------------------------


@dataclass
class StaticFileProvider:
    """Writes the rendered email to ``{root}/static_outbox/{id}/...`` and
    returns a synthetic message id.

    Used in dev and tests where we want to inspect the rendered output
    without standing up a real SMTP server. Never raises on the happy
    path; failures are filesystem-only (permission errors etc.) and
    propagate as plain ``OSError`` so the service-layer retry logic can
    catch them.
    """

    root: Path

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body_html: str,
        body_text: str | None,
        attachments: list[Attachment],
        from_address: str,
    ) -> ProviderResult:
        message_id = f"static-{uuid.uuid4()}"
        outbox = self.root / "static_outbox" / message_id
        outbox.mkdir(parents=True, exist_ok=True)
        # Loop returns control between writes — playing nice with the
        # event loop even though sync IO is fast enough here.
        await asyncio.to_thread(
            self._write_files, outbox, to, subject, from_address, body_html, body_text, attachments
        )
        return ProviderResult(provider_message_id=message_id, status="sent")

    @staticmethod
    def _write_files(
        outbox: Path,
        to: str,
        subject: str,
        from_address: str,
        body_html: str,
        body_text: str | None,
        attachments: list[Attachment],
    ) -> None:
        header = f"From: {from_address}\n" f"To: {to}\n" f"Subject: {subject}\n\n"
        (outbox / "message.eml").write_text(header + body_html, encoding="utf-8")
        if body_text is not None:
            (outbox / "body.txt").write_text(body_text, encoding="utf-8")
        for att in attachments:
            (outbox / att.filename).write_bytes(att.content)


# ---------------------------------------------------------------------------
# SmtpProvider
# ---------------------------------------------------------------------------


@dataclass
class SmtpProvider:
    """Sends via SMTP using ``aiosmtplib``.

    The dataclass holds the connection params. ``send`` builds a
    ``email.message.EmailMessage``, attaches each :class:`Attachment` as
    a binary MIME part, and dispatches.
    """

    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body_html: str,
        body_text: str | None,
        attachments: list[Attachment],
        from_address: str,
    ) -> ProviderResult:
        # Import inside the method so test collection on machines without
        # aiosmtplib (e.g. the dispatcher's defensive imports) doesn't
        # explode at module load.
        from email.message import EmailMessage

        import aiosmtplib

        msg = EmailMessage()
        msg["From"] = from_address
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body_text or "")
        msg.add_alternative(body_html, subtype="html")

        for att in attachments:
            maintype, _, subtype = att.content_type.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(
                att.content,
                maintype=maintype,
                subtype=subtype,
                filename=att.filename,
            )

        await aiosmtplib.send(
            msg,
            hostname=self.host,
            port=self.port,
            username=self.username or None,
            password=self.password or None,
            start_tls=self.use_tls,
        )
        # SMTP doesn't return a real id; synthesize one so the column has
        # something useful.
        return ProviderResult(
            provider_message_id=f"smtp-{uuid.uuid4()}",
            status="sent",
        )


# ---------------------------------------------------------------------------
# SesProvider (stub)
# ---------------------------------------------------------------------------


@dataclass
class SesProvider:
    """STUB. AWS SES integration is OUT OF SCOPE for Phase 7.7.

    Left as a clear seam so a later phase can drop in ``boto3`` /
    ``aiobotocore`` without touching the service layer. Today: raises.
    """

    region: str | None = None

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body_html: str,
        body_text: str | None,
        attachments: list[Attachment],
        from_address: str,
    ) -> ProviderResult:
        # TODO(phase-7.8+): replace with real SES delivery.
        raise NotImplementedError(
            "SesProvider is a stub — set email.provider to 'static_file' "
            "or 'smtp' until a Phase 7.8+ branch lands SES support."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


async def get_email_provider(*, session: AsyncSession) -> EmailProvider:
    """Resolve the configured provider for the current settings snapshot.

    Reads ``email.provider`` for the explicit override; falls back to
    ``static_file`` whenever ``email.smtp_host`` is empty even when the
    provider key says ``smtp`` — that way a forgotten host config doesn't
    silently swallow every outbound email.
    """
    from app.services.settings.service import SettingsService

    provider_key = (await SettingsService.get("email.provider", session=session)) or "static_file"
    smtp_host = await SettingsService.get("email.smtp_host", session=session) or ""
    root = Path(str(await SettingsService.get("email.storage_root", session=session)))

    if provider_key == "smtp" and smtp_host:
        smtp_port = await SettingsService.get("email.smtp_port", session=session)
        smtp_username = await SettingsService.get("email.smtp_username", session=session) or ""
        smtp_password = (
            await SettingsService.get("email.smtp_password_secret", session=session) or ""
        )
        return SmtpProvider(
            host=str(smtp_host),
            port=int(smtp_port),
            username=str(smtp_username),
            password=str(smtp_password),
        )
    if provider_key == "ses":
        return SesProvider()
    # Default: static_file (covers empty-smtp-host fallback too).
    return StaticFileProvider(root=root)


__all__ = [
    "Attachment",
    "EmailProvider",
    "ProviderResult",
    "SesProvider",
    "SmtpProvider",
    "StaticFileProvider",
    "get_email_provider",
]
