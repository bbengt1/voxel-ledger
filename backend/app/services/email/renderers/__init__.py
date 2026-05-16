"""Email renderers (Phase 7.7, #115).

Each renderer is one ``async def render(...) -> Rendered`` function that
loads its subject (quote / invoice / statement) and returns a
:class:`Rendered` tuple of ``subject``, ``body_html``, ``body_text``,
and a list of :class:`Attachment`. The service layer takes that tuple
and persists it as one ``email_message`` row.

Templates live under ``backend/app/templates/email/`` and are loaded via
a module-level Jinja2 ``Environment`` so the same FS lookup is reused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.email.providers import Attachment

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    enable_async=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def get_template(name: str):
    return _env.get_template(name)


@dataclass
class Rendered:
    subject: str
    body_html: str
    body_text: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


__all__ = ["Rendered", "TEMPLATES_DIR", "get_template"]
