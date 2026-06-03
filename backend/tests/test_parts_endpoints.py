"""Parts API: role matrix, CRUD, validation, list/search (epic #267 Phase 1)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

_FIXTURES = Path(__file__).parent / "fixtures"


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-{uuid.uuid4().hex[:6]}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/parts")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.SALES, 201),
        (Role.BOOKKEEPER, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token(role, client, app_session)
    r = await client.post(
        "/api/v1/parts",
        headers=_h(token),
        json={"name": f"Widget {role.value}", "print_minutes": 60, "parts_per_run": 2},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_autoallocates_sku_and_roundtrips_recipe(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    material_id = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/parts",
        headers=_h(owner),
        json={
            "name": "Bracket",
            "description": "left bracket",
            "print_minutes": 90,
            "setup_minutes": 5,
            "parts_per_run": 4,
            "print_grams_by_material": {material_id: "12.5"},
            "assigned_printer_ids": [],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sku"].startswith("PART-")
    assert body["parts_per_run"] == 4
    assert body["print_minutes"] == 90
    assert body["print_grams_by_material"][material_id] == "12.5"
    # Phase 2a: the part_cost projection computes the cost on create (here
    # from print/labor/machine since the random material has no priced
    # receipt). With default rate config it resolves to a value.
    assert body["unit_cost_cached"] is not None

    # Fetch round-trip.
    got = await client.get(f"/api/v1/parts/{body['id']}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["name"] == "Bracket"


@pytest.mark.asyncio
async def test_duplicate_manual_sku_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    first = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "A", "sku": "PART-CUSTOM-1"}
    )
    assert first.status_code == 201
    dup = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "B", "sku": "PART-CUSTOM-1"}
    )
    assert dup.status_code == 400, dup.text


@pytest.mark.asyncio
async def test_parts_per_run_must_be_positive(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "Bad", "parts_per_run": 0}
    )
    # Schema enforces gt=0 → 422.
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_update_and_archive_cycle(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "Editable", "print_minutes": 10}
    )
    pid = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/parts/{pid}",
        headers=_h(owner),
        json={"name": "Renamed", "print_minutes": 20},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["print_minutes"] == 20

    arch = await client.post(f"/api/v1/parts/{pid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    unarch = await client.post(f"/api/v1/parts/{pid}/unarchive", headers=_h(owner))
    assert unarch.status_code == 200
    assert unarch.json()["is_archived"] is False


@pytest.mark.asyncio
async def test_list_search_and_archived_filter(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Alpha gear"})
    b = await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Beta gear"})
    await client.post(f"/api/v1/parts/{b.json()['id']}/archive", headers=_h(owner))

    found = await client.get("/api/v1/parts", headers=_h(owner), params={"search": "alpha"})
    names = [p["name"] for p in found.json()["items"]]
    assert "Alpha gear" in names and "Beta gear" not in names

    active = await client.get("/api/v1/parts", headers=_h(owner), params={"is_archived": "false"})
    active_names = [p["name"] for p in active.json()["items"]]
    assert "Beta gear" not in active_names


@pytest.mark.asyncio
async def test_get_unknown_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.get(f"/api/v1/parts/{uuid.uuid4()}", headers=_h(owner))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_and_get_report_total_on_hand(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    from decimal import Decimal

    from app.services import inventory_transactions as inventory_tx_service

    owner = await _token(Role.OWNER, client, app_session)
    stocked = (
        await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Stocked gear"})
    ).json()
    empty = (
        await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Empty gear"})
    ).json()

    # Seed 7 on hand for the stocked part.
    await inventory_tx_service.record(
        app_session,
        kind="production_in",
        entity_kind="part",
        entity_id=uuid.UUID(stocked["id"]),
        location_id=workshop_location.id,
        quantity=Decimal("7"),
        actor_user_id=None,
        reason="test seed",
    )
    await app_session.commit()

    listing = await client.get("/api/v1/parts", headers=_h(owner))
    by_id = {p["id"]: p for p in listing.json()["items"]}
    assert Decimal(by_id[stocked["id"]]["total_on_hand"]) == Decimal("7")
    # A part with no inventory rows still reports 0 (not missing/null).
    assert Decimal(by_id[empty["id"]]["total_on_hand"]) == Decimal("0")

    one = await client.get(f"/api/v1/parts/{stocked['id']}", headers=_h(owner))
    assert Decimal(one.json()["total_on_hand"]) == Decimal("7")


# ---------------------------------------------------------------------------
# gcode discovery → pre-fill the part recipe (carried over from job entry)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_part_recipe_from_sidecar(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(Role.PRODUCTION, client, app_session)
    content = (_FIXTURES / "prusaslicer_sample.gcode.json").read_bytes()
    r = await client.post(
        "/api/v1/parts/discover",
        headers=_h(token),
        files={"file": ("prusaslicer_sample.gcode.json", content, "application/json")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Same parser as the legacy job discovery: 2h15m30s -> 135 min, 3 parts.
    assert body["print_minutes"] == 135
    assert body["parts_per_set"] == 3
    assert body["source_format"] == "prusaslicer"
    # Filament is keyed by slicer slot (operator maps slot -> material in UI).
    assert body["filament_grams_by_material"]["slot_0"] == "42.5"


@pytest.mark.asyncio
async def test_discover_part_recipe_rejects_garbage(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(Role.PRODUCTION, client, app_session)
    r = await client.post(
        "/api/v1/parts/discover",
        headers=_h(token),
        files={"file": ("junk.gcode.json", b"not-json{{{", "application/json")},
    )
    assert r.status_code in (400, 415), r.text


@pytest.mark.asyncio
async def test_discover_part_recipe_requires_auth(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/parts/discover",
        files={"file": ("x.gcode.json", b"{}", "application/json")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_discover_part_recipe_from_printer(
    client: AsyncClient, app_session: AsyncSession, monkeypatch
) -> None:
    from app.services import job_discovery
    from app.services import printers as printers_service
    from app.services.job_discovery import DiscoveredPlate

    token = await _token(Role.PRODUCTION, client, app_session)
    printer = await printers_service.create(
        app_session,
        name="Voron",
        slug=f"voron-{uuid.uuid4().hex[:6]}",
        printer_type="other",
        moonraker_url="http://printer.invalid:7125",
        moonraker_api_key=None,
        actor_user_id=None,
    )
    await app_session.commit()

    seen: dict[str, object] = {}

    async def fake_fetch(*, moonraker_url: str, api_key: str | None, filename: str):
        seen.update(moonraker_url=moonraker_url, api_key=api_key, filename=filename)
        return DiscoveredPlate(
            print_minutes=60,
            filament_grams_by_material={"PLA": __import__("decimal").Decimal("20.5")},
            parts_per_set=2,
            source_format="prusaslicer",
            source_filename=filename,
        )

    monkeypatch.setattr(job_discovery, "discover_from_moonraker", fake_fetch)

    r = await client.post(
        "/api/v1/parts/discover-from-printer",
        headers=_h(token),
        json={"printer_id": str(printer.id), "filename": "bracket.gcode"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["print_minutes"] == 60
    assert body["parts_per_set"] == 2
    assert body["filament_grams_by_material"]["PLA"] == "20.5"
    assert body["source_filename"] == "bracket.gcode"
    # The endpoint resolved the printer's Moonraker URL + key for the fetch.
    assert seen["moonraker_url"] == "http://printer.invalid:7125"
    assert seen["filename"] == "bracket.gcode"


@pytest.mark.asyncio
async def test_discover_from_printer_404_when_no_moonraker(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    from app.services import printers as printers_service

    token = await _token(Role.PRODUCTION, client, app_session)
    printer = await printers_service.create(
        app_session,
        name="No-Moonraker",
        slug=f"nm-{uuid.uuid4().hex[:6]}",
        printer_type="other",
        moonraker_url=None,
        moonraker_api_key=None,
        actor_user_id=None,
    )
    await app_session.commit()
    r = await client.post(
        "/api/v1/parts/discover-from-printer",
        headers=_h(token),
        json={"printer_id": str(printer.id), "filename": "x.gcode"},
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_discover_from_printer_502_on_fetch_error(
    client: AsyncClient, app_session: AsyncSession, monkeypatch
) -> None:
    from app.services import job_discovery
    from app.services import printers as printers_service

    token = await _token(Role.PRODUCTION, client, app_session)
    printer = await printers_service.create(
        app_session,
        name="Flaky",
        slug=f"flaky-{uuid.uuid4().hex[:6]}",
        printer_type="other",
        moonraker_url="http://printer.invalid:7125",
        moonraker_api_key=None,
        actor_user_id=None,
    )
    await app_session.commit()

    async def boom(**_kwargs):
        raise job_discovery.MoonrakerFetchError("connection refused")

    monkeypatch.setattr(job_discovery, "discover_from_moonraker", boom)
    r = await client.post(
        "/api/v1/parts/discover-from-printer",
        headers=_h(token),
        json={"printer_id": str(printer.id), "filename": "x.gcode"},
    )
    assert r.status_code == 502, r.text


@pytest.mark.asyncio
async def test_discover_from_printer_requires_auth(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/parts/discover-from-printer",
        json={"printer_id": str(uuid.uuid4()), "filename": "x.gcode"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Attach a printer gcode thumbnail as the part image
# ---------------------------------------------------------------------------


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


async def _set_storage_root(session: AsyncSession, path) -> None:
    from app.services.settings.service import SettingsService

    await SettingsService.set(
        "attachments.storage_root", str(path), session=session, actor_user_id=None
    )
    await session.commit()


@pytest.mark.asyncio
async def test_attach_part_image_from_printer(
    client: AsyncClient, app_session: AsyncSession, monkeypatch, tmp_path
) -> None:
    from app.services import job_discovery
    from app.services import printers as printers_service

    await _set_storage_root(app_session, tmp_path)
    owner = await _token(Role.OWNER, client, app_session)
    created = await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Imaged"})
    part_id = created.json()["id"]
    printer = await printers_service.create(
        app_session,
        name="Voron",
        slug=f"voron-{uuid.uuid4().hex[:6]}",
        printer_type="other",
        moonraker_url="http://printer.invalid:7125",
        moonraker_api_key=None,
        actor_user_id=None,
    )
    await app_session.commit()

    async def fake_thumb(*, moonraker_url, api_key, filename):
        return _png_bytes()

    monkeypatch.setattr(job_discovery, "fetch_moonraker_thumbnail", fake_thumb)

    r = await client.post(
        f"/api/v1/parts/{part_id}/image/from-printer",
        headers=_h(owner),
        json={"printer_id": str(printer.id), "filename": "bracket.gcode"},
    )
    assert r.status_code == 204, r.text

    # The image is now retrievable.
    img = await client.get(f"/api/v1/parts/{part_id}/image", headers=_h(owner))
    assert img.status_code == 200


@pytest.mark.asyncio
async def test_attach_part_image_from_printer_404_when_no_thumbnail(
    client: AsyncClient, app_session: AsyncSession, monkeypatch
) -> None:
    from app.services import job_discovery
    from app.services import printers as printers_service

    owner = await _token(Role.OWNER, client, app_session)
    created = await client.post("/api/v1/parts", headers=_h(owner), json={"name": "NoImg"})
    part_id = created.json()["id"]
    printer = await printers_service.create(
        app_session,
        name="Voron2",
        slug=f"voron-{uuid.uuid4().hex[:6]}",
        printer_type="other",
        moonraker_url="http://printer.invalid:7125",
        moonraker_api_key=None,
        actor_user_id=None,
    )
    await app_session.commit()

    async def no_thumb(*, moonraker_url, api_key, filename):
        return None

    monkeypatch.setattr(job_discovery, "fetch_moonraker_thumbnail", no_thumb)
    r = await client.post(
        f"/api/v1/parts/{part_id}/image/from-printer",
        headers=_h(owner),
        json={"printer_id": str(printer.id), "filename": "plain.gcode"},
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_discover_returns_embedded_thumbnail_b64(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    import base64
    import json as _json

    token = await _token(Role.PRODUCTION, client, app_session)
    png = _png_bytes()
    doc = {
        "estimated_printing_time_normal_mode": "1h",
        "filament_used_g": [10.0],
        "thumbnails": [{"data": base64.b64encode(png).decode(), "width": 300, "height": 300}],
    }
    r = await client.post(
        "/api/v1/parts/discover",
        headers=_h(token),
        files={"file": ("part.gcode.json", _json.dumps(doc).encode(), "application/json")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["thumbnail_b64"] is not None
    assert base64.b64decode(body["thumbnail_b64"]) == png


@pytest.mark.asyncio
async def test_discover_thumbnail_b64_none_without_embed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(Role.PRODUCTION, client, app_session)
    content = (_FIXTURES / "prusaslicer_sample.gcode.json").read_bytes()
    r = await client.post(
        "/api/v1/parts/discover",
        headers=_h(token),
        files={"file": ("prusaslicer_sample.gcode.json", content, "application/json")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["thumbnail_b64"] is None
