"""Generic entity-image service (assembly-line epic #267, generalized from #259).

One primary image per entity (product, part, …), stored on local disk
under the ``attachments.storage_root`` setting. On upload the image is
normalized into two WEBP renditions — ``full`` (max 1024px) and ``thumb``
(max 256px) — under ``<kind>-images/<entity_id>/``. No DB column tracks
presence: callers learn an image exists by requesting it (404 when absent).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.attachments.storage import resolve_storage_root, safe_write

ALLOWED_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB

_FULL_MAX = (1024, 1024)
_THUMB_MAX = (256, 256)
_SIZES = ("full", "thumb")


class EntityImageError(Exception):
    """Bad upload (non-image, too large, undecodable). Router maps to 400."""


def _rel_path(kind: str, entity_id: uuid.UUID, size: str) -> Path:
    return Path(f"{kind}-images") / str(entity_id) / f"{size}.webp"


def _render(content: bytes, max_size: tuple[int, int]) -> bytes:
    try:
        img = Image.open(BytesIO(content))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise EntityImageError("file is not a decodable image") from exc
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
    else:
        img = img.convert("RGB")
    img.thumbnail(max_size)
    out = BytesIO()
    img.save(out, format="WEBP", quality=85)
    return out.getvalue()


async def save(
    *,
    session: AsyncSession,
    kind: str,
    entity_id: uuid.UUID,
    content: bytes,
    content_type: str | None,
) -> None:
    """Validate + render the upload into ``full`` and ``thumb`` WEBP files."""
    if content_type is not None and content_type.lower() not in ALLOWED_MIME_TYPES:
        raise EntityImageError(f"unsupported image type {content_type!r}; allowed: PNG, JPEG, WEBP")
    if len(content) > MAX_UPLOAD_BYTES:
        raise EntityImageError("image exceeds the 10 MiB limit")
    if not content:
        raise EntityImageError("empty upload")

    root = await resolve_storage_root(session=session)
    full = _render(content, _FULL_MAX)
    thumb = _render(content, _THUMB_MAX)
    safe_write(full, root / _rel_path(kind, entity_id, "full"))
    safe_write(thumb, root / _rel_path(kind, entity_id, "thumb"))


async def path_for(
    *, session: AsyncSession, kind: str, entity_id: uuid.UUID, size: str
) -> Path | None:
    """Absolute path to a rendition, or None when no image is stored."""
    if size not in _SIZES:
        size = "full"
    root = await resolve_storage_root(session=session)
    path = root / _rel_path(kind, entity_id, size)
    return path if path.exists() else None


async def delete(*, session: AsyncSession, kind: str, entity_id: uuid.UUID) -> bool:
    """Remove both renditions. Returns True if anything was deleted."""
    root = await resolve_storage_root(session=session)
    removed = False
    for size in _SIZES:
        path = root / _rel_path(kind, entity_id, size)
        if path.exists():
            path.unlink()
            removed = True
    return removed
