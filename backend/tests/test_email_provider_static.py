"""StaticFileProvider unit test (Phase 7.7, #115)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.email.providers import Attachment, StaticFileProvider


@pytest.mark.asyncio
async def test_static_file_provider_writes_files(tmp_path: Path) -> None:
    provider = StaticFileProvider(root=tmp_path)
    result = await provider.send(
        to="dest@example.com",
        subject="Hello",
        body_html="<p>hi</p>",
        body_text="hi",
        attachments=[Attachment(filename="x.pdf", content=b"%PDF-1.4 stub")],
        from_address="sender@example.com",
    )
    assert result.provider_message_id.startswith("static-")
    assert result.status == "sent"
    outbox = tmp_path / "static_outbox" / result.provider_message_id
    assert outbox.is_dir()
    eml = (outbox / "message.eml").read_text(encoding="utf-8")
    assert "dest@example.com" in eml
    assert "Subject: Hello" in eml
    assert "<p>hi</p>" in eml
    assert (outbox / "body.txt").read_text(encoding="utf-8") == "hi"
    assert (outbox / "x.pdf").read_bytes() == b"%PDF-1.4 stub"
