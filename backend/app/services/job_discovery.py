"""Job-discovery sidecar parser (Phase 5.5, #81).

Parses ``.gcode.json`` sidecar files produced by PrusaSlicer and Bambu
Studio into a :class:`DiscoveredPlate` dataclass that the UI can use to
pre-fill a plate form. **No DB writes** — the operator clicks
"use these values" in the UI and the existing ``PlatesService.create``
flow creates the real plate.

Why a dataclass instead of touching the model?
----------------------------------------------
The two slicers identify filament by *spool slot*, not by material UUID.
We can't map a spool slot to a ``material_id`` without operator
intervention. The discover endpoint returns the parsed values; the
operator picks the real material in the UI.

Format detection
----------------
We don't trust the filename. The JSON itself is structurally distinctive:

* PrusaSlicer-style: top-level keys include ``estimated_printing_time_normal_mode``
  or ``filament_used_g`` (often a list keyed by extruder).
* Bambu Studio-style: top-level ``plates`` array each with a ``prediction``
  (seconds), ``weight`` (grams total), and per-filament ``filament_maps``.

If neither shape matches we raise :class:`UnknownSidecarFormatError`.

The parser is forgiving: missing minor fields default to ``0``. It is
*not* forgiving about top-level structure — that's the whole point of
clearly rejecting unknown formats.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from xml.etree import ElementTree as ET

import httpx


class JobDiscoveryError(Exception):
    """Base class. Routers map subclasses to 400."""


class UnknownSidecarFormatError(JobDiscoveryError):
    """Couldn't identify the format from the JSON shape."""


class MalformedSidecarError(JobDiscoveryError):
    """The JSON parsed but a required field was the wrong shape."""


@dataclass
class DiscoveredPlate:
    print_minutes: int
    filament_grams_by_material: dict[str, Decimal] = field(default_factory=dict)
    parts_per_set: int = 1
    source_format: str = "unknown"
    source_filename: str | None = None


# Match "1h 23m 45s" / "12m 30s" / "5h" — PrusaSlicer formats vary by
# build but always look like one or more ``\d+[hms]`` chunks.
_TIME_TOKEN_RE = re.compile(r"(\d+)\s*([hms])")


def _parse_time_to_minutes(value: object) -> int:
    """Best-effort parse of a slicer time string or numeric seconds."""
    if isinstance(value, int | float):
        # Numeric — treat as seconds (Bambu's ``prediction`` field).
        return max(0, int(round(float(value) / 60.0)))
    if not isinstance(value, str):
        return 0
    stripped = value.strip()
    # Bambu's 3MF stores ``prediction`` as a bare-number string of
    # seconds. Honor that path before falling to the h/m/s regex so we
    # don't silently return 0 for an otherwise valid time.
    try:
        return max(0, int(round(float(stripped) / 60.0)))
    except ValueError:
        pass
    total_seconds = 0
    for amount, unit in _TIME_TOKEN_RE.findall(stripped):
        n = int(amount)
        if unit == "h":
            total_seconds += n * 3600
        elif unit == "m":
            total_seconds += n * 60
        else:
            total_seconds += n
    return max(0, total_seconds // 60)


def _coerce_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return Decimal("0")


def _looks_prusa(doc: dict) -> bool:
    return any(
        k in doc
        for k in (
            "estimated_printing_time_normal_mode",
            "estimated_printing_time",
            "filament_used_g",
            "filament_used_mm",
        )
    )


def _looks_bambu(doc: dict) -> bool:
    plates = doc.get("plates")
    if not isinstance(plates, list) or not plates:
        return False
    first = plates[0]
    if not isinstance(first, dict):
        return False
    return any(k in first for k in ("prediction", "weight", "filament_maps", "objects"))


def _parse_prusaslicer(doc: dict) -> DiscoveredPlate:
    minutes = _parse_time_to_minutes(
        doc.get("estimated_printing_time_normal_mode") or doc.get("estimated_printing_time") or 0
    )

    grams_field = doc.get("filament_used_g")
    grams_by_slot: dict[str, Decimal] = {}
    if isinstance(grams_field, list):
        for idx, val in enumerate(grams_field):
            grams_by_slot[f"slot_{idx}"] = _coerce_decimal(val)
    elif isinstance(grams_field, int | float | str):
        grams_by_slot["slot_0"] = _coerce_decimal(grams_field)
    elif isinstance(grams_field, dict):
        for k, v in grams_field.items():
            grams_by_slot[str(k)] = _coerce_decimal(v)

    parts_per_set = 1
    raw_objects = doc.get("objects")
    if isinstance(raw_objects, list) and raw_objects:
        parts_per_set = len(raw_objects)
    elif isinstance(doc.get("object_count"), int) and doc["object_count"] > 0:
        parts_per_set = int(doc["object_count"])

    return DiscoveredPlate(
        print_minutes=minutes,
        filament_grams_by_material=grams_by_slot,
        parts_per_set=max(1, parts_per_set),
        source_format="prusaslicer",
    )


def _parse_bambu(doc: dict) -> DiscoveredPlate:
    plates = doc.get("plates") or []
    if not plates:
        raise MalformedSidecarError("Bambu sidecar has no plates")
    plate = plates[0]
    if not isinstance(plate, dict):
        raise MalformedSidecarError("Bambu sidecar plate entry is not an object")

    minutes = _parse_time_to_minutes(plate.get("prediction") or plate.get("time") or 0)

    grams_by_slot: dict[str, Decimal] = {}
    filaments = plate.get("filaments") or plate.get("filament_maps")
    if isinstance(filaments, list):
        for idx, item in enumerate(filaments):
            if isinstance(item, dict):
                # Bambu format: {"id": "...", "used_g": "12.3"} or
                # {"tray_id": 2, "weight": 12.3}
                used = item.get("used_g") or item.get("weight") or item.get("filament_used_g") or 0
                slot = item.get("id") or item.get("tray_id") or item.get("extruder_id") or idx
                grams_by_slot[f"slot_{slot}"] = _coerce_decimal(used)
            else:
                grams_by_slot[f"slot_{idx}"] = _coerce_decimal(item)
    elif isinstance(filaments, dict):
        for k, v in filaments.items():
            grams_by_slot[str(k)] = _coerce_decimal(v)

    if not grams_by_slot and "weight" in plate:
        grams_by_slot["slot_0"] = _coerce_decimal(plate.get("weight"))

    objects = plate.get("objects")
    parts_per_set = (
        len(objects)
        if isinstance(objects, list) and objects
        else int(plate.get("object_count") or 1)
    )

    return DiscoveredPlate(
        print_minutes=minutes,
        filament_grams_by_material=grams_by_slot,
        parts_per_set=max(1, parts_per_set),
        source_format="bambu",
    )


def parse_gcode_sidecar(
    file_bytes: bytes, *, source_filename: str | None = None
) -> DiscoveredPlate:
    """Parse a slicer ``.gcode.json`` sidecar into a :class:`DiscoveredPlate`.

    Raises :class:`UnknownSidecarFormatError` for anything we don't
    recognize — never silently return zeros.
    """
    if not file_bytes:
        raise MalformedSidecarError("empty sidecar")
    try:
        doc = json.loads(file_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSidecarError(f"not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise UnknownSidecarFormatError(
            "sidecar root must be a JSON object — got " f"{type(doc).__name__}"
        )

    if _looks_prusa(doc):
        result = _parse_prusaslicer(doc)
    elif _looks_bambu(doc):
        result = _parse_bambu(doc)
    else:
        raise UnknownSidecarFormatError(
            "could not identify slicer sidecar format; expected "
            "PrusaSlicer or Bambu Studio .gcode.json shape"
        )

    result.source_filename = source_filename
    return result


# ---------------------------------------------------------------------------
# 3MF support
# ---------------------------------------------------------------------------
#
# A 3MF is a zip archive. "Sliced" 3MFs from Bambu Studio, OrcaSlicer, or
# PrusaSlicer carry a per-plate metadata file we can parse without
# touching the slicer pipeline:
#
#   Bambu / Orca: ``Metadata/slice_info.config`` — XML, one ``<plate>``
#     per print plate, with ``<metadata key="prediction" value="…"/>``
#     for time and ``<filament … used_g="…"/>`` per spool.
#   PrusaSlicer:  ``Metadata/Slic3r_PE.config`` — flat ``key = value``
#     pairs, same vocabulary as the gcode header that ``parse_gcode_sidecar``
#     already understands.
#
# Unsliced 3MFs contain only geometry — we reject them with a clear
# message rather than guessing.

_3MF_BAMBU_CONFIG = "Metadata/slice_info.config"
_3MF_PRUSA_CONFIGS = (
    "Metadata/Slic3r_PE.config",
    "Metadata/Slic3r_PE_model.config",
)


def _is_zip(file_bytes: bytes) -> bool:
    return file_bytes[:4] == b"PK\x03\x04"


def _read_member(zf: zipfile.ZipFile, name: str) -> str | None:
    """Case-insensitive zip member read. Returns ``None`` if missing."""
    needle = name.lower()
    for info in zf.infolist():
        if info.filename.lower() == needle:
            try:
                return zf.read(info).decode("utf-8", errors="replace")
            except KeyError:
                return None
    return None


def _parse_bambu_3mf(xml_text: str) -> DiscoveredPlate:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise MalformedSidecarError(f"3MF slice_info.config is not valid XML: {exc}") from exc

    plates = root.findall(".//plate")
    if not plates:
        # Bambu / Orca write a header-only ``slice_info.config`` when
        # the project was saved but never sliced. Surface that as the
        # same "slice it first" error as a model-only 3MF rather than
        # a malformed-file error.
        raise UnknownSidecarFormatError(
            "3MF was saved before slicing — open it in Bambu Studio or "
            "OrcaSlicer, slice all plates, then re-export the .3mf."
        )

    # Use the first plate. Multi-plate prints can have more added by hand
    # in the composer if needed.
    plate = plates[0]

    minutes = 0
    parts_per_set = 1
    for meta in plate.findall("metadata"):
        key = meta.get("key") or ""
        value = meta.get("value")
        if value is None:
            continue
        if key == "prediction":
            minutes = _parse_time_to_minutes(value)
        elif key == "object_count" and value.isdigit():
            parts_per_set = max(parts_per_set, int(value))

    # ``<object>`` children describe distinct printed objects on this
    # plate. Bambu reports them with ``skipped="false"`` when they
    # actually print; treat any non-skipped object as part of the set.
    objects = [
        o for o in plate.findall("object") if (o.get("skipped") or "false").lower() != "true"
    ]
    if objects:
        parts_per_set = max(parts_per_set, len(objects))

    grams_by_slot: dict[str, Decimal] = {}
    for fil in plate.findall("filament"):
        used = fil.get("used_g") or fil.get("weight")
        if used is None:
            continue
        # Prefer a human-readable label (type/colour) over the raw slot
        # id so the discovered-name hint on the form is useful. Fall back
        # to the slot id when neither is present.
        fil_type = (fil.get("type") or "").strip()
        fil_color = (fil.get("color") or "").strip()
        fil_id = (fil.get("id") or "").strip()
        if fil_type and fil_color:
            label = f"{fil_type} {fil_color}"
        elif fil_type:
            label = fil_type
        elif fil_id:
            label = f"slot_{fil_id}"
        else:
            label = f"slot_{len(grams_by_slot)}"
        # If two slots collide on the same label, accumulate grams.
        existing = grams_by_slot.get(label, Decimal("0"))
        grams_by_slot[label] = existing + _coerce_decimal(used)

    return DiscoveredPlate(
        print_minutes=minutes,
        filament_grams_by_material=grams_by_slot,
        parts_per_set=max(1, parts_per_set),
        source_format="bambu_3mf",
    )


def _parse_prusa_3mf_config(text: str) -> DiscoveredPlate:
    """Parse PrusaSlicer's ``Slic3r_PE.config`` (gcode-header-style keys).

    Lines look like ``; estimated printing time (normal mode) = 1h 23m`` or
    ``; filament used [g] = 12.34,5.67``.
    """
    minutes = 0
    grams_by_slot: dict[str, Decimal] = {}
    parts_per_set = 1
    for raw_line in text.splitlines():
        line = raw_line.lstrip("; ").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if "estimated printing time" in key:
            minutes = _parse_time_to_minutes(value)
        elif key.startswith("filament used [g]"):
            for idx, item in enumerate(value.split(",")):
                grams_by_slot[f"slot_{idx}"] = _coerce_decimal(item.strip())
        elif key in ("objects_info", "object_count") and value.isdigit() and int(value) > 0:
            parts_per_set = max(parts_per_set, int(value))
    if minutes == 0 and not grams_by_slot:
        raise MalformedSidecarError("PrusaSlicer 3MF config had no print time or filament data")
    return DiscoveredPlate(
        print_minutes=minutes,
        filament_grams_by_material=grams_by_slot,
        parts_per_set=max(1, parts_per_set),
        source_format="prusaslicer_3mf",
    )


def parse_3mf(file_bytes: bytes, *, source_filename: str | None = None) -> DiscoveredPlate:
    """Parse a sliced 3MF archive into a :class:`DiscoveredPlate`.

    Raises :class:`UnknownSidecarFormatError` for an unsliced 3MF (no
    slicer metadata inside) and :class:`MalformedSidecarError` when the
    metadata we find is broken.
    """
    if not _is_zip(file_bytes):
        raise UnknownSidecarFormatError("3MF must be a zip archive")
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise MalformedSidecarError(f"corrupt 3MF zip: {exc}") from exc

    with zf:
        bambu_text = _read_member(zf, _3MF_BAMBU_CONFIG)
        if bambu_text:
            result = _parse_bambu_3mf(bambu_text)
            result.source_filename = source_filename
            return result
        for member_name in _3MF_PRUSA_CONFIGS:
            prusa_text = _read_member(zf, member_name)
            if prusa_text:
                result = _parse_prusa_3mf_config(prusa_text)
                result.source_filename = source_filename
                return result

    raise UnknownSidecarFormatError(
        "3MF doesn't contain slicer metadata — slice it in Bambu Studio, "
        "OrcaSlicer, or PrusaSlicer first, then re-upload."
    )


def parse_job_artifact(file_bytes: bytes, *, source_filename: str | None = None) -> DiscoveredPlate:
    """Dispatch by content: ``.3mf`` (zip) vs ``.gcode.json`` (JSON).

    Callers should hand the raw upload bytes to this function rather
    than picking the parser themselves — the JSON vs. zip distinction
    is unambiguous from the first few bytes.
    """
    if not file_bytes:
        raise MalformedSidecarError("empty upload")
    if _is_zip(file_bytes):
        return parse_3mf(file_bytes, source_filename=source_filename)
    return parse_gcode_sidecar(file_bytes, source_filename=source_filename)


# ---------------------------------------------------------------------------
# Moonraker (discover-from-printer)
# ---------------------------------------------------------------------------

_MOONRAKER_TIMEOUT_SECONDS = 8.0


class MoonrakerFetchError(JobDiscoveryError):
    """Could not fetch metadata from the printer's Moonraker."""


def parse_moonraker_metadata(meta: dict, *, source_filename: str | None = None) -> DiscoveredPlate:
    """Map a Moonraker ``/server/files/metadata`` result into a
    :class:`DiscoveredPlate` — the same shape the sidecar parser returns.

    Moonraker exposes ``estimated_time`` (seconds), per-extruder
    ``filament_weight`` + ``filament_name`` (``;``-joined), and sometimes
    ``object_count``. Filament is keyed by name (or ``slot_N``); the
    operator maps each to a real material in the UI.
    """
    estimated = meta.get("estimated_time")
    print_minutes = (
        int((float(estimated) + 59.0) // 60.0) if isinstance(estimated, int | float) else 0
    )

    grams_by_slot: dict[str, Decimal] = {}
    weights = meta.get("filament_weight")
    names_raw = meta.get("filament_name") or ""
    names: list[str] = [s.strip(' "') for s in str(names_raw).split(";")] if names_raw else []
    if isinstance(weights, list):
        for idx, weight in enumerate(weights):
            if not isinstance(weight, int | float) or weight <= 0:
                continue
            label = names[idx].strip() if idx < len(names) and names[idx].strip() else f"slot_{idx}"
            grams_by_slot[label] = Decimal(str(weight))

    parts_per_set_raw = meta.get("object_count")
    parts_per_set = (
        int(parts_per_set_raw)
        if isinstance(parts_per_set_raw, int | float) and parts_per_set_raw > 0
        else 1
    )

    return DiscoveredPlate(
        print_minutes=print_minutes,
        filament_grams_by_material=grams_by_slot,
        parts_per_set=parts_per_set,
        source_format=str(meta.get("slicer") or "moonraker"),
        source_filename=source_filename,
    )


async def discover_from_moonraker(
    *, moonraker_url: str, api_key: str | None, filename: str
) -> DiscoveredPlate:
    """Fetch + parse one gcode file's Moonraker metadata into a
    :class:`DiscoveredPlate`. Raises :class:`MoonrakerFetchError` on any
    network/HTTP failure so the caller can surface a 502.
    """
    base = moonraker_url.rstrip("/")
    headers: dict[str, str] = {"X-Api-Key": api_key} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=_MOONRAKER_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{base}/server/files/metadata",
                params={"filename": filename},
                headers=headers,
            )
            resp.raise_for_status()
            meta = resp.json().get("result") or {}
    except Exception as exc:
        raise MoonrakerFetchError(str(exc)) from exc
    return parse_moonraker_metadata(meta, source_filename=filename)


__all__ = [
    "DiscoveredPlate",
    "JobDiscoveryError",
    "MalformedSidecarError",
    "MoonrakerFetchError",
    "UnknownSidecarFormatError",
    "discover_from_moonraker",
    "parse_3mf",
    "parse_gcode_sidecar",
    "parse_job_artifact",
    "parse_moonraker_metadata",
]
