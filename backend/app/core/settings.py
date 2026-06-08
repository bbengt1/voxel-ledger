"""Application settings.

Loaded from environment via pydantic-settings. Refuses to start when required
secrets are missing or contain obvious placeholder values.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# CORS origin parsing: accept either a JSON list or a comma-separated string
# from the environment. Comma-separated wins on operator ergonomics; the
# validator below normalizes both shapes into a list[str].

# Exact-match sentinels: reject the value outright when it equals any of these
# (case-insensitive, stripped).
PLACEHOLDER_EXACT = frozenset(
    {
        "",
        "change-me",
        "changeme",
        "change_me",
        "replace-me",
        "replaceme",
        "replace_me",
        "your-secret-here",
        "your_secret_here",
        "secret",
        "password",
        "todo",
        "tbd",
        "xxx",
    }
)

# Substring sentinels: reject if they appear *anywhere* in the value. Kept
# narrow so we don't false-positive on real high-entropy secrets that happen
# to contain "xxx" or "secret" as random characters.
PLACEHOLDER_SUBSTRINGS = frozenset(
    {
        "change-me",
        "changeme",
        "change_me",
        "replace-me",
        "replace_me",
        "your-secret-here",
        "your_secret_here",
    }
)

SECRET_FIELDS = frozenset(
    {
        "jwt_secret_key",
        "database_url",
        "owner_email",
        "owner_password",
        "qbo_client_secret",
        "secret_encryption_key",
    }
)


class Settings(BaseSettings):
    """Backend configuration.

    Each secret-bearing field is validated against a placeholder denylist so
    a forgotten `.env.example` value cannot bring the service up by accident.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App metadata
    app_name: str = "voxel-ledger-backend"
    app_version: str = "0.1.0"
    environment: Literal["dev", "test", "prod"] = "dev"
    testing: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = Field(
        ...,
        description="SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pw@host/db",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False

    # Security / Auth
    jwt_secret_key: str = Field(..., min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_seconds: int = 2_592_000  # 30 days
    bcrypt_rounds: int = 12
    login_rate_limit_per_minute: int = 10

    # CORS — allow-list of browser origins permitted to call the API.
    # Empty list disables the CORS middleware entirely (server-to-server only).
    # NoDecode disables pydantic-settings' default JSON parser so the validator
    # below can accept both JSON (`["a","b"]`) and comma-separated (`a,b`)
    # forms from env.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Seed owner (only consumed by scripts/seed_owner.py). Optional so the
    # app can boot without seed creds set; the seed script will raise if
    # they're missing at run time. When provided, placeholder values are
    # still rejected.
    owner_email: str | None = None
    owner_password: str | None = None

    # QuickBooks Online OAuth (epic #312, Phase 1 #314). Optional so the app
    # boots without QBO configured; the /admin/quickbooks connect flow raises a
    # clear error if these are unset. `qbo_client_secret` is placeholder-checked.
    # Phase-0 verified base config: sandbox vs production via `qbo_environment`.
    qbo_client_id: str | None = None
    qbo_client_secret: str | None = None
    qbo_redirect_uri: str | None = None
    qbo_environment: Literal["sandbox", "production"] = "sandbox"

    # Secret-at-rest encryption (epic #312 hardening). A single Fernet key used
    # to encrypt sensitive DB columns — currently the QBO OAuth tokens (see
    # app/core/crypto.py + docs/secrets-at-rest.md). Optional so the app boots
    # without it; only required when an encrypted secret is actually read or
    # written. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_encryption_key: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept comma-separated strings from env, JSON lists, or actual lists."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            # JSON list form: ["http://a", "http://b"]. We parse here because
            # NoDecode on the field disables the default JSON decoding.
            if stripped.startswith("["):
                return json.loads(stripped)
            # Comma-separated form: "http://a,http://b"
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator(
        "database_url",
        "jwt_secret_key",
        "owner_email",
        "owner_password",
        "qbo_client_secret",
        "secret_encryption_key",
    )
    @classmethod
    def _reject_placeholders(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.field_name not in SECRET_FIELDS:
            return value
        if value is None:
            return value
        token = value.strip().lower()
        if token in PLACEHOLDER_EXACT:
            raise ValueError(
                f"{info.field_name} contains a placeholder value "
                f"({value!r}); set a real value in the environment."
            )
        for sentinel in PLACEHOLDER_SUBSTRINGS:
            if sentinel in token:
                raise ValueError(
                    f"{info.field_name} appears to embed placeholder text "
                    f"({sentinel!r}); replace it before starting the app."
                )
        return value


def load_settings() -> Settings:
    """Construct Settings.

    Wrapped in a function so tests can monkeypatch env and re-load without
    fighting module-level caching.
    """
    return Settings()  # type: ignore[call-arg]
