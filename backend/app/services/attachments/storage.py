"""Local-disk storage helpers for attachments (Phase 2.6).

The storage root comes from the ``attachments.storage_root`` setting. We
resolve it lazily so contributors can override at runtime (PUT on the
settings endpoint) without restarting the app. Per-attachment paths are
``{YYYY}/{MM}/{uuid4}-{slug(filename)}`` — UUID-prefixed so two uploads
of the same filename cannot collide.

Writes are atomic: ``safe_write`` writes to a ``.partial`` sibling, then
calls ``os.replace`` to swap into the final path. On crash the
``.partial`` will be left behind; a future garbage collector can sweep
it, but it's never visible through the API.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.service import SettingsService

# Replace anything that isn't alnum, dash, underscore, or dot.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

SLUG_MAX_LEN = 100


def slugify_filename(filename: str) -> str:
    """Return a filesystem-safe slug derived from the original filename.

    Truncates to ``SLUG_MAX_LEN`` characters and collapses runs of unsafe
    characters into a single underscore. Empty results fall back to
    ``"file"`` so the on-disk basename always has a body.
    """
    name = (filename or "").strip()
    # Take only the basename in case the client smuggled a path.
    name = Path(name).name
    name = _UNSAFE.sub("_", name).strip("._-")
    if not name:
        name = "file"
    if len(name) > SLUG_MAX_LEN:
        # Preserve the extension if it fits in the budget.
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) + 1 < SLUG_MAX_LEN:
            keep = SLUG_MAX_LEN - len(ext) - 1
            name = stem[:keep] + "." + ext
        else:
            name = name[:SLUG_MAX_LEN]
    return name


def compute_storage_path(filename: str, *, now: datetime | None = None) -> str:
    """Compute the relative storage path for a new attachment.

    Format: ``YYYY/MM/<uuid4>-<slug>``. Returned as a string (forward
    slashes) — the caller joins it under the resolved root.
    """
    now = now or datetime.now(UTC)
    slug = slugify_filename(filename)
    return f"{now.year:04d}/{now.month:02d}/{uuid.uuid4()}-{slug}"


async def resolve_storage_root(*, session: AsyncSession) -> Path:
    """Read the ``attachments.storage_root`` setting and return a Path.

    Does NOT create the directory — the caller does that lazily on the
    first write so a typo'd config doesn't crash boot.
    """
    raw = await SettingsService.get("attachments.storage_root", session=session)
    return Path(str(raw))


def safe_write(content: bytes, dest_path: Path) -> None:
    """Atomically write ``content`` to ``dest_path``.

    1. Ensure parent dir exists.
    2. Write to a ``.partial`` sibling.
    3. ``os.replace`` it onto the final path.

    On any failure between (2) and (3) the .partial file remains; the
    final path is never written half-formed.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    partial = dest_path.with_suffix(dest_path.suffix + ".partial")
    with open(partial, "wb") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(partial, dest_path)


__all__ = [
    "SLUG_MAX_LEN",
    "compute_storage_path",
    "resolve_storage_root",
    "safe_write",
    "slugify_filename",
]
