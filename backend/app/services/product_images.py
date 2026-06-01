"""Product image service (#259).

Thin product-specific wrapper over the generic ``entity_images`` service
(epic #267 generalized this so parts can reuse the same renditions logic).
Public surface is unchanged: product images live under ``product-images/``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import entity_images
from app.services.entity_images import ALLOWED_MIME_TYPES, MAX_UPLOAD_BYTES

# Back-compat alias: callers catch ``product_images.ProductImageError``.
ProductImageError = entity_images.EntityImageError

_KIND = "product"

__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_UPLOAD_BYTES",
    "ProductImageError",
    "delete",
    "path_for",
    "save",
]


async def save(
    *,
    session: AsyncSession,
    product_id: uuid.UUID,
    content: bytes,
    content_type: str | None,
) -> None:
    await entity_images.save(
        session=session,
        kind=_KIND,
        entity_id=product_id,
        content=content,
        content_type=content_type,
    )


async def path_for(*, session: AsyncSession, product_id: uuid.UUID, size: str):
    return await entity_images.path_for(
        session=session, kind=_KIND, entity_id=product_id, size=size
    )


async def delete(*, session: AsyncSession, product_id: uuid.UUID) -> bool:
    return await entity_images.delete(session=session, kind=_KIND, entity_id=product_id)
