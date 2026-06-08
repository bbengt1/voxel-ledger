"""Settings validation — placeholder rejection is the headline behavior."""

from __future__ import annotations

import pytest
from app.core.settings import Settings
from pydantic import ValidationError


def _ok_kwargs(**overrides: object) -> dict[str, object]:
    base = {
        "database_url": "postgresql+asyncpg://user:realpw@db:5432/voxel",
        "jwt_secret_key": "x" * 48,
    }
    base.update(overrides)
    return base


def test_settings_accepts_real_values() -> None:
    s = Settings(**_ok_kwargs())  # type: ignore[arg-type]
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert len(s.jwt_secret_key) >= 16


@pytest.mark.parametrize(
    "placeholder",
    ["change-me", "changeme", "replace-me", "your-secret-here", ""],
)
def test_settings_rejects_placeholder_jwt(placeholder: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok_kwargs(jwt_secret_key=placeholder))  # type: ignore[arg-type]


def test_settings_rejects_embedded_placeholder_in_db_url() -> None:
    bad = "postgresql+asyncpg://user:change-me@db:5432/voxel"
    with pytest.raises(ValidationError):
        Settings(**_ok_kwargs(database_url=bad))  # type: ignore[arg-type]


def test_settings_rejects_empty_db_url() -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok_kwargs(database_url=""))  # type: ignore[arg-type]


@pytest.mark.parametrize("placeholder", ["change-me", "your-secret-here", ""])
def test_settings_rejects_placeholder_encryption_key(placeholder: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok_kwargs(secret_encryption_key=placeholder))  # type: ignore[arg-type]


def test_settings_encryption_key_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unset is allowed; the app boots without it and only needs it when an
    # encrypted secret is read/written. (conftest seeds the env key, so clear
    # it here to exercise the unset path.)
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    s = Settings(**_ok_kwargs())  # type: ignore[arg-type]
    assert s.secret_encryption_key is None


def test_app_refuses_to_start_with_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory should refuse a placeholder-bearing Settings outright."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:change-me@h/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)

    from app.core.settings import load_settings

    with pytest.raises(ValidationError):
        load_settings()
