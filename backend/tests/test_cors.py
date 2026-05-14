"""CORS middleware wiring — lock in the cross-origin allow-list behavior."""

from __future__ import annotations

import pytest
from app.core.settings import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def _ok_kwargs(**overrides: object) -> dict[str, object]:
    base = {
        "database_url": "postgresql+asyncpg://user:realpw@db:5432/voxel",
        "jwt_secret_key": "x" * 48,
    }
    base.update(overrides)
    return base


def test_cors_origins_parses_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:realpw@h/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://localhost:3000")

    from app.core.settings import load_settings

    s = load_settings()
    assert s.cors_origins == ["http://localhost:5173", "http://localhost:3000"]


def test_cors_origins_parses_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:realpw@h/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173"]')

    from app.core.settings import load_settings

    s = load_settings()
    assert s.cors_origins == ["http://localhost:5173"]


def test_cors_origins_empty_by_default() -> None:
    s = Settings(**_ok_kwargs())  # type: ignore[arg-type]
    assert s.cors_origins == []


def test_cors_middleware_emits_allow_origin_header() -> None:
    s = Settings(**_ok_kwargs(cors_origins=["http://localhost:5173"]))  # type: ignore[arg-type]
    app = create_app(s)
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_middleware_disabled_when_origins_empty() -> None:
    s = Settings(**_ok_kwargs())  # type: ignore[arg-type]
    app = create_app(s)
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:5173"})
        # No middleware = no CORS headers on the response.
        assert "access-control-allow-origin" not in response.headers
