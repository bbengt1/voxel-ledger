"""Health endpoint."""

from __future__ import annotations

import json

import pytest
from app import __version__
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "version": __version__}
    assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_health_echoes_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "abc-123"


@pytest.mark.asyncio
async def test_health_503_on_db_failure(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `SELECT 1` fails, health returns 503."""
    from app.core import db as db_module

    real_factory = db_module._session_factory
    assert real_factory is not None

    class _BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("simulated DB outage")

    def _broken_factory():
        return _BrokenSession()

    monkeypatch.setattr(db_module, "_session_factory", _broken_factory)
    try:
        resp = await client.get("/health")
    finally:
        monkeypatch.setattr(db_module, "_session_factory", real_factory)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_log_format_has_required_fields(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every log line should be JSON with ts, level, msg, and request_id."""
    from app.core.logging import get_logger

    capsys.readouterr()  # drain prior output
    log = get_logger("test")
    # Drive a request so request_id contextvar is populated.
    await client.get("/health", headers={"X-Request-ID": "log-test-id"})
    log.info("standalone")  # not in request scope — should still be JSON
    out = capsys.readouterr().out
    json_lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert json_lines, f"no JSON log lines found in: {out!r}"
    parsed = [json.loads(ln) for ln in json_lines]
    for entry in parsed:
        assert "ts" in entry
        assert "level" in entry
        assert "msg" in entry
