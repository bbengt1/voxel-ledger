"""Placeholder rejection for the auth-related settings."""

from __future__ import annotations

import pytest
from app.core.settings import Settings
from pydantic import ValidationError


def _ok(**overrides: object) -> dict[str, object]:
    base = {
        "database_url": "postgresql+asyncpg://user:realpw@db:5432/voxel",
        "jwt_secret_key": "x" * 48,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "placeholder",
    ["change-me", "changeme", "replace-me", "your-secret-here", ""],
)
def test_owner_email_rejects_placeholder(placeholder: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok(owner_email=placeholder))  # type: ignore[arg-type]


@pytest.mark.parametrize("placeholder", ["change-me", "changeme", "replace-me", ""])
def test_owner_password_rejects_placeholder(placeholder: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok(owner_password=placeholder))  # type: ignore[arg-type]


def test_owner_email_with_embedded_sentinel_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok(owner_email="real-change-me@example.com"))  # type: ignore[arg-type]


def test_owner_fields_optional_when_unset() -> None:
    s = Settings(**_ok())  # type: ignore[arg-type]
    assert s.owner_email is None
    assert s.owner_password is None


def test_jwt_secret_placeholder_still_blocked() -> None:
    with pytest.raises(ValidationError):
        Settings(**_ok(jwt_secret_key="change-me"))  # type: ignore[arg-type]
