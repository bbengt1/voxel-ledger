"""Job-discovery sidecar parser (Phase 5.5, #81)."""

from __future__ import annotations

import io
import zipfile
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


# ---------------------------------------------------------------------------
# 3MF support
# ---------------------------------------------------------------------------


def _make_3mf(members: dict[str, str]) -> bytes:
    """Build an in-memory 3MF zip with the given member paths."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buf.getvalue()


_BAMBU_SLICE_INFO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="24224"/>
    <metadata key="weight" value="176.53"/>
    <object identify_id="1" name="part_a" skipped="false"/>
    <object identify_id="2" name="part_b" skipped="false"/>
    <object identify_id="3" name="part_c" skipped="true"/>
    <filament id="1" type="PLA" color="#000000" used_m="41.83" used_g="124.76"/>
    <filament id="2" type="PLA" color="#FFFFFF" used_m="16.30" used_g="51.77"/>
  </plate>
</config>
"""


def test_parses_bambu_3mf() -> None:
    data = _make_3mf({"Metadata/slice_info.config": _BAMBU_SLICE_INFO_XML})
    result = job_discovery.parse_job_artifact(data, source_filename="round_light.3mf")
    assert result.source_format == "bambu_3mf"
    # 24224 seconds → 404 minutes (Bambu rounds via integer math; the
    # sidecar parser rounds half-up to match).
    assert result.print_minutes == 404
    # Two non-skipped objects on the plate.
    assert result.parts_per_set == 2
    # Filaments stored under human-readable "TYPE COLOR" labels.
    assert result.filament_grams_by_material["PLA #000000"] == Decimal("124.76")
    assert result.filament_grams_by_material["PLA #FFFFFF"] == Decimal("51.77")
    assert result.source_filename == "round_light.3mf"


def test_parses_prusaslicer_3mf() -> None:
    config = (
        "; estimated printing time (normal mode) = 1h 23m 45s\n" "; filament used [g] = 42.5,7.25\n"
    )
    data = _make_3mf({"Metadata/Slic3r_PE.config": config})
    result = job_discovery.parse_job_artifact(data, source_filename="thing.3mf")
    assert result.source_format == "prusaslicer_3mf"
    assert result.print_minutes == 83
    assert result.filament_grams_by_material["slot_0"] == Decimal("42.5")
    assert result.filament_grams_by_material["slot_1"] == Decimal("7.25")


def test_unsliced_3mf_rejected_with_clear_message() -> None:
    # Pure geometry, no slicer metadata.
    data = _make_3mf({"3D/3dmodel.model": "<model/>"})
    with pytest.raises(job_discovery.UnknownSidecarFormatError) as exc:
        job_discovery.parse_job_artifact(data, source_filename="raw.3mf")
    assert "slice it" in str(exc.value).lower()


def test_bambu_3mf_header_only_slice_info_treated_as_unsliced() -> None:
    """Bambu/Orca writes a header-only slice_info.config when a project
    is saved before slicing — surface the same "slice it first" error
    as a model-only 3MF."""
    header_only = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="02.06.01.55"/>
  </header>
</config>
"""
    data = _make_3mf({"Metadata/slice_info.config": header_only})
    with pytest.raises(job_discovery.UnknownSidecarFormatError) as exc:
        job_discovery.parse_job_artifact(data, source_filename="usa.3mf")
    assert "slice" in str(exc.value).lower()


def test_dispatcher_routes_json_to_sidecar_parser() -> None:
    # The dispatcher should still handle the existing .gcode.json path.
    result = job_discovery.parse_job_artifact(
        _load("prusaslicer_sample.gcode.json"),
        source_filename="prusaslicer_sample.gcode.json",
    )
    assert result.source_format == "prusaslicer"


# ---------------------------------------------------------------------------
# Moonraker metadata mapping (discover-from-printer)
# ---------------------------------------------------------------------------


def test_parse_moonraker_metadata_maps_recipe() -> None:
    meta = {
        "estimated_time": 3600,  # seconds → 60 min
        "filament_weight": [20.5, 3.0],
        "filament_name": "PLA; PETG",
        "object_count": 2,
        "slicer": "PrusaSlicer",
    }
    plate = job_discovery.parse_moonraker_metadata(meta, source_filename="part.gcode")
    assert plate.print_minutes == 60
    assert plate.parts_per_set == 2
    assert plate.filament_grams_by_material["PLA"] == Decimal("20.5")
    assert plate.filament_grams_by_material["PETG"] == Decimal("3.0")
    assert plate.source_format == "PrusaSlicer"
    assert plate.source_filename == "part.gcode"


def test_parse_moonraker_metadata_defaults_on_sparse() -> None:
    plate = job_discovery.parse_moonraker_metadata({}, source_filename="x.gcode")
    assert plate.print_minutes == 0
    assert plate.parts_per_set == 1
    assert plate.filament_grams_by_material == {}
    assert plate.source_format == "moonraker"
