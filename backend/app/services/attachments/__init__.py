"""Attachments service package (Phase 2.6).

Re-exports the service-layer surface so callers can do
``from app.services import attachments as attachments_service`` exactly
like the other services. The actual implementation lives in
``app.services.attachments.service``; the storage helpers live in
``app.services.attachments.storage``.
"""

from __future__ import annotations

from app.services.attachments.service import (
    ALLOWED_MIME_PREFIXES,
    ALLOWED_MIME_TYPES,
    MAX_BYTE_SIZE,
    AttachmentNotFoundError,
    AttachmentPage,
    AttachmentPermissionError,
    AttachmentsServiceError,
    InvalidCursorError,
    InvalidMimeTypeError,
    OversizeAttachmentError,
    archive,
    download,
    get,
    list_for,
    upload,
)
from app.services.attachments.storage import (
    compute_storage_path,
    resolve_storage_root,
    safe_write,
    slugify_filename,
)

__all__ = [
    "ALLOWED_MIME_PREFIXES",
    "ALLOWED_MIME_TYPES",
    "AttachmentNotFoundError",
    "AttachmentPage",
    "AttachmentPermissionError",
    "AttachmentsServiceError",
    "InvalidCursorError",
    "InvalidMimeTypeError",
    "MAX_BYTE_SIZE",
    "OversizeAttachmentError",
    "archive",
    "compute_storage_path",
    "download",
    "get",
    "list_for",
    "resolve_storage_root",
    "safe_write",
    "slugify_filename",
    "upload",
]
