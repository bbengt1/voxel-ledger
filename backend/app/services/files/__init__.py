"""Generalized local-FS blob storage (Phase 7.3, #111).

Lifts the "configurable root + atomic write + read-by-key" pattern out
of ``services.shipping.storage`` so it can host invoice PDFs as well as
labels. The shipping storage helpers still live in their own module for
back-compat; new callers (invoices) use this one.

The settings registry pattern is unchanged — each caller registers its
own ``*.storage_root`` key. Callers pass the root path explicitly so
this module stays settings-agnostic.
"""

from __future__ import annotations

import os
from pathlib import Path


def safe_write(content: bytes, dest_path: Path) -> None:
    """Atomic write: ``.partial`` + ``os.replace``."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    partial = dest_path.with_suffix(dest_path.suffix + ".partial")
    with open(partial, "wb") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(partial, dest_path)


def write_blob(content: bytes, *, root: Path, storage_key: str) -> None:
    """Persist ``content`` under ``{root}/{storage_key}``."""
    safe_write(content, root / storage_key)


def read_blob(storage_key: str, *, root: Path) -> bytes | None:
    """Read the blob under ``{root}/{storage_key}`` or ``None`` if missing."""
    path = root / storage_key
    if not path.is_file():
        return None
    with open(path, "rb") as fh:
        return fh.read()


__all__ = ["read_blob", "safe_write", "write_blob"]
