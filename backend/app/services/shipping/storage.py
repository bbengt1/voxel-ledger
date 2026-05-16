"""Label-PDF storage helpers (Phase 6.6, #98).

For now we only support a local-FS backend that lives under the
``shipping.labels_storage_root`` setting. Keys are ``shipping-labels/{
shipment_id}.pdf``. The S3 backend is a Phase 6.7+ concern; the API
shape here intentionally keeps "store this blob under this key" and
"read this blob by key" as separate functions so swapping backends is a
service-level change, not a router change.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.service import SettingsService


def label_storage_key(shipment_id: uuid.UUID) -> str:
    """The canonical storage key for ``shipment_id``'s PDF."""
    return f"shipping-labels/{shipment_id}.pdf"


async def resolve_labels_root(*, session: AsyncSession) -> Path:
    """Resolve the configured filesystem root.

    Reads ``shipping.labels_storage_root`` (string). Does NOT create the
    directory — the writer does that lazily on the first PUT so a
    typo'd config doesn't crash boot.
    """
    raw = await SettingsService.get("shipping.labels_storage_root", session=session)
    return Path(str(raw))


def safe_write(content: bytes, dest_path: Path) -> None:
    """Atomic write: write ``.partial``, then ``os.replace``.

    Mirrors ``attachments.storage.safe_write``. Lifted into its own
    function here because the attachments helper would also pull in the
    attachments service's allowlist logic if we re-used it directly,
    and the surface area we need is tiny.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    partial = dest_path.with_suffix(dest_path.suffix + ".partial")
    with open(partial, "wb") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(partial, dest_path)


async def write_label_pdf(
    pdf_bytes: bytes,
    *,
    storage_key: str,
    session: AsyncSession,
) -> None:
    """Persist ``pdf_bytes`` under ``storage_key`` in the configured root."""
    root = await resolve_labels_root(session=session)
    safe_write(pdf_bytes, root / storage_key)


async def read_label_pdf(
    storage_key: str,
    *,
    session: AsyncSession,
) -> bytes | None:
    """Read the PDF stored under ``storage_key``.

    Returns ``None`` when no file exists at that key (covers both the
    "we never wrote a label" case and the "the file got deleted out from
    under us" case so the router can 404 either way).
    """
    root = await resolve_labels_root(session=session)
    path = root / storage_key
    if not path.is_file():
        return None
    with open(path, "rb") as fh:
        return fh.read()


__all__ = [
    "label_storage_key",
    "read_label_pdf",
    "resolve_labels_root",
    "safe_write",
    "write_label_pdf",
]
