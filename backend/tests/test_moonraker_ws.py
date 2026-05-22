"""Moonraker WS connector tests (Issue #222).

Pluggable transport pattern: each test injects a fake
``connect_factory`` so the client runs against an in-memory
``FakeConnection`` instead of a real Moonraker. The fake captures
sent messages, lets the test feed inbound notifications, and can
fail on demand to exercise the reconnect path.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from datetime import UTC, datetime

import pytest
from app.services.printer_monitor.ws import (
    MoonrakerWsClient,
    StatusUpdate,
)


class FakeConnection:
    """In-memory websocket. Tests drive it by ``await
    push(payload_dict)``; consumption shows up to the client's
    ``__aiter__`` loop."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        while True:
            msg = await self._queue.get()
            if msg is None:  # close sentinel
                return
            yield msg

    async def close(self) -> None:
        self.closed = True
        await self._queue.put(None)

    async def push(self, payload: dict) -> None:
        await self._queue.put(json.dumps(payload))

    async def push_close(self) -> None:
        await self._queue.put(None)


def _notify_status(payload: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "notify_status_update",
        "params": [payload, 12.34],
    }


@pytest.mark.asyncio
async def test_subscribes_on_connect_and_dispatches_updates() -> None:
    received: list[StatusUpdate] = []
    conn = FakeConnection()

    async def factory(url, *, headers=None, open_timeout=10.0):
        _ = url, headers, open_timeout
        return conn

    async def on_status(update: StatusUpdate) -> None:
        received.append(update)

    client = MoonrakerWsClient(
        printer_id=uuid.uuid4(),
        ws_url="ws://printer.local/websocket",
        api_key="secret",
        on_status=on_status,
        connect_factory=factory,
    )
    await client.start()
    # Give the loop a tick to connect + subscribe.
    for _ in range(20):
        if conn.sent:
            break
        await asyncio.sleep(0.01)

    assert len(conn.sent) == 1
    sub = json.loads(conn.sent[0])
    assert sub["method"] == "printer.objects.subscribe"
    assert "print_stats" in sub["params"]["objects"]

    await conn.push(
        _notify_status(
            {
                "print_stats": {
                    "state": "printing",
                    "filename": "model.gcode",
                    "print_duration": 600,
                },
                "display_status": {"progress": 0.42},
                "extruder": {"temperature": 200.5},
                "heater_bed": {"temperature": 60.0},
            }
        )
    )
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.01)

    await client.stop()

    assert len(received) == 1
    update = received[0]
    assert update.state == "printing"
    assert update.current_file == "model.gcode"
    assert update.progress_pct == pytest.approx(42.0)
    assert update.extruder_temp == 200.5
    assert update.bed_temp == 60.0
    assert client.status.last_event_at is not None


@pytest.mark.asyncio
async def test_reconnect_after_connect_failure() -> None:
    attempts = {"n": 0}
    conn = FakeConnection()

    async def factory(url, *, headers=None, open_timeout=10.0):
        _ = url, headers, open_timeout
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("nope")
        return conn

    async def on_status(_: StatusUpdate) -> None:
        return

    client = MoonrakerWsClient(
        printer_id=uuid.uuid4(),
        ws_url="ws://printer.local/websocket",
        api_key=None,
        on_status=on_status,
        connect_factory=factory,
        rng=random.Random(0),
    )
    await client.start()

    for _ in range(200):
        if client.status.connected:
            break
        await asyncio.sleep(0.05)
    await client.stop()

    assert attempts["n"] >= 2
    assert client.status.reconnect_count >= 1


@pytest.mark.asyncio
async def test_disconnect_then_reconnect() -> None:
    conns: list[FakeConnection] = []

    async def factory(url, *, headers=None, open_timeout=10.0):
        _ = url, headers, open_timeout
        c = FakeConnection()
        conns.append(c)
        return c

    async def on_status(_: StatusUpdate) -> None:
        return

    client = MoonrakerWsClient(
        printer_id=uuid.uuid4(),
        ws_url="ws://printer.local/websocket",
        api_key=None,
        on_status=on_status,
        connect_factory=factory,
        rng=random.Random(0),
    )
    await client.start()
    for _ in range(50):
        if conns:
            break
        await asyncio.sleep(0.01)
    assert conns
    # First connection lands.
    await asyncio.sleep(0.05)
    assert client.status.connected

    # Force a disconnect.
    await conns[0].push_close()
    for _ in range(200):
        if len(conns) >= 2:
            break
        await asyncio.sleep(0.02)
    await client.stop()
    assert len(conns) >= 2  # reconnected at least once
    assert client.status.reconnect_count >= 2


@pytest.mark.asyncio
async def test_callback_exception_does_not_kill_listener() -> None:
    received: list[StatusUpdate] = []
    conn = FakeConnection()

    async def factory(url, *, headers=None, open_timeout=10.0):
        _ = url, headers, open_timeout
        return conn

    async def on_status(update: StatusUpdate) -> None:
        received.append(update)
        raise RuntimeError("callback boom")

    client = MoonrakerWsClient(
        printer_id=uuid.uuid4(),
        ws_url="ws://printer.local/websocket",
        api_key=None,
        on_status=on_status,
        connect_factory=factory,
    )
    await client.start()
    await asyncio.sleep(0.05)
    await conn.push(_notify_status({"print_stats": {"state": "idle"}}))
    await conn.push(_notify_status({"print_stats": {"state": "printing"}}))
    for _ in range(50):
        if len(received) >= 2:
            break
        await asyncio.sleep(0.02)
    await client.stop()
    assert len(received) >= 2  # listener kept running


@pytest.mark.asyncio
async def test_status_update_from_moonraker_partial_payload() -> None:
    # Real-world Moonraker pushes delta updates — fields are often
    # absent on a given notification. The parser must not blow up.
    update = StatusUpdate.from_moonraker(
        printer_id=uuid.uuid4(),
        payload={"print_stats": {"state": "paused"}},
    )
    assert update.state == "paused"
    assert update.progress_pct is None
    assert update.current_file is None
    assert update.elapsed_seconds is None
    assert update.extruder_temp is None


def test_status_update_received_at_is_utc() -> None:
    update = StatusUpdate.from_moonraker(
        printer_id=uuid.uuid4(),
        payload={"print_stats": {"state": "idle"}},
    )
    assert update.received_at.tzinfo is not None
    assert (datetime.now(UTC) - update.received_at).total_seconds() < 2
