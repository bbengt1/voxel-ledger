"""SmtpProvider unit test (Phase 7.7, #115).

Mocks ``aiosmtplib.send`` to verify the SmtpProvider builds the message
correctly and dispatches with the configured host/port.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.services.email.providers import Attachment, SmtpProvider


@pytest.mark.asyncio
async def test_smtp_provider_send_builds_message() -> None:
    provider = SmtpProvider(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pw",
    )
    with patch("aiosmtplib.send", new=AsyncMock()) as send_mock:
        result = await provider.send(
            to="to@example.com",
            subject="Hi",
            body_html="<p>html</p>",
            body_text="text",
            attachments=[
                Attachment(filename="r.pdf", content=b"%PDF-1.4", content_type="application/pdf"),
            ],
            from_address="from@example.com",
        )
    assert send_mock.await_count == 1
    kwargs = send_mock.await_args.kwargs
    assert kwargs["hostname"] == "smtp.example.com"
    assert kwargs["port"] == 587
    assert kwargs["username"] == "user"
    assert kwargs["password"] == "pw"
    msg = send_mock.await_args.args[0]
    assert msg["To"] == "to@example.com"
    assert msg["Subject"] == "Hi"
    assert msg["From"] == "from@example.com"

    assert result.provider_message_id.startswith("smtp-")
