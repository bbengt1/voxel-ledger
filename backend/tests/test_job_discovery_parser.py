"""Job-discovery sidecar parser (Phase 5.5, #81)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from app.services import job_discovery

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parses_prusaslicer_sidecar() -> None:
    result = job_discovery.parse_gcode_sidecar(
        _load("prusaslicer_sample.gcode.json"),
        source_filename="prusaslicer_sample.gcode.json",
    )
    assert result.source_format == "prusaslicer"
    # 2h 15m 30s = 8130s → 135 minutes (seconds truncated by integer math).
    assert result.print_minutes == 135
    assert result.parts_per_set == 3
    assert result.filament_grams_by_material["slot_0"] == Decimal("42.5")
    assert result.filament_grams_by_material["slot_1"] == Decimal("7.25")
    assert result.source_filename == "prusaslicer_sample.gcode.json"


def test_parses_bambu_sidecar() -> None:
    result = job_discovery.parse_gcode_sidecar(_load("bambu_sample.gcode.json"))
    assert result.source_format == "bambu"
    # 4530 seconds -> 75 minutes (rounded).
    assert result.print_minutes == 76
    assert result.parts_per_set == 2
    # Bambu uses tray/extruder slots.
    grams = result.filament_grams_by_material
    assert any(v == Decimal("22.1") for v in grams.values())
    assert any(v == Decimal("16.3") for v in grams.values())


def test_rejects_unknown_format() -> None:
    with pytest.raises(job_discovery.UnknownSidecarFormatError):
        job_discovery.parse_gcode_sidecar(_load("unknown_sample.gcode.json"))


def test_rejects_invalid_json() -> None:
    with pytest.raises(job_discovery.MalformedSidecarError):
        job_discovery.parse_gcode_sidecar(b"not-json{{{")


def test_rejects_non_object_root() -> None:
    with pytest.raises(job_discovery.UnknownSidecarFormatError):
        job_discovery.parse_gcode_sidecar(b"[1, 2, 3]")


def test_rejects_empty() -> None:
    with pytest.raises(job_discovery.MalformedSidecarError):
        job_discovery.parse_gcode_sidecar(b"")
