"""Canonical serialization + hash determinism. Pure functions, no DB."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest
from app.services.event_store import (
    GENESIS_PREV_HASH,
    canonical_bytes,
    compute_event_hash,
)


def _sample_row() -> dict[str, object]:
    return {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "position": 1,
        "type": "test.TestEvent",
        "aggregate_type": "test",
        "aggregate_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "payload": {"value": "hello"},
        "occurred_at": datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC),
        "recorded_at": datetime(2026, 5, 14, 12, 0, 1, tzinfo=UTC),
        "actor_user_id": None,
        "correlation_id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
        "causation_id": None,
        "prev_event_hash": GENESIS_PREV_HASH,
        "schema_version": 1,
    }


def test_canonical_bytes_is_deterministic_under_key_reordering() -> None:
    row1 = _sample_row()
    row2 = {k: row1[k] for k in reversed(list(row1))}
    assert canonical_bytes(row1) == canonical_bytes(row2)


def test_canonical_bytes_sorts_nested_keys() -> None:
    """``sort_keys=True`` applies to all levels; payload key order must
    not change the hash."""
    row1 = _sample_row()
    row1["payload"] = {"a": 1, "b": 2}
    row2 = _sample_row()
    row2["payload"] = {"b": 2, "a": 1}
    assert canonical_bytes(row1) == canonical_bytes(row2)


def test_canonical_bytes_excludes_event_hash() -> None:
    row = _sample_row()
    a = canonical_bytes(row)
    row["event_hash"] = "deadbeef" * 8
    b = canonical_bytes(row)
    assert a == b


def test_canonical_bytes_includes_prev_event_hash() -> None:
    row1 = _sample_row()
    row2 = _sample_row()
    row2["prev_event_hash"] = "f" * 64
    assert canonical_bytes(row1) != canonical_bytes(row2)


def test_compute_event_hash_matches_sha256_of_canonical_bytes() -> None:
    row = _sample_row()
    expected = hashlib.sha256(canonical_bytes(row)).hexdigest()
    assert compute_event_hash(row) == expected


def test_uuid_and_datetime_serialize_as_strings() -> None:
    row = _sample_row()
    encoded = json.loads(canonical_bytes(row).decode("utf-8"))
    assert encoded["id"] == "11111111-1111-1111-1111-111111111111"
    assert encoded["occurred_at"].startswith("2026-05-14T12:00:00")
    assert encoded["occurred_at"].endswith("+00:00")


def test_naive_datetime_rejected() -> None:
    row = _sample_row()
    row["occurred_at"] = datetime(2026, 5, 14, 12, 0, 0)  # naive
    with pytest.raises(TypeError):
        canonical_bytes(row)


def test_genesis_prev_hash_is_64_zeros() -> None:
    assert GENESIS_PREV_HASH == "0" * 64
    assert len(GENESIS_PREV_HASH) == 64


def test_hash_changes_when_payload_changes() -> None:
    row1 = _sample_row()
    row2 = _sample_row()
    row2["payload"] = {"value": "different"}
    assert compute_event_hash(row1) != compute_event_hash(row2)
