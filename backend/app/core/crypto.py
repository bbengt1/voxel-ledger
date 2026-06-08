"""Symmetric encryption for secrets at rest (Fernet).

This is the **new standard** for storing third-party secrets in the database
(see ``docs/secrets-at-rest.md``). Today it protects the QuickBooks Online
OAuth tokens (``oauth_credential.access_token`` / ``refresh_token`` — epic
#312), which grant access to the company's live books. The older plaintext
secrets (``email.smtp_password_secret``, ``camera.password_secret``,
``moonraker_api_key``) are candidates to migrate onto this helper next.

Design:

* A single Fernet key, sourced from ``Settings.secret_encryption_key`` (env
  ``SECRET_ENCRYPTION_KEY``), drives all encrypt/decrypt operations. Generate
  one with ``python -c "from cryptography.fernet import Fernet;
  print(Fernet.generate_key().decode())"``.
* :class:`EncryptedString` is a SQLAlchemy ``TypeDecorator`` that encrypts on
  write and decrypts on read, so model/service code keeps handling plaintext
  ``str`` values — the ciphertext only ever exists in the column.
* The cipher is loaded lazily (and cached) from :func:`app.core.settings.load_settings`
  the first time a value is encrypted/decrypted. The key is therefore only
  required when secret columns are actually read or written, so an app with no
  connected integrations (and no rows to decrypt) boots without it.

Fernet provides authenticated symmetric encryption (AES-128-CBC + HMAC-SHA256),
so a wrong/rotated key surfaces as a clear :class:`SecretEncryptionError` rather
than silently returning garbage.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class SecretEncryptionError(RuntimeError):
    """The encryption key is missing/invalid, or a value failed to decrypt."""


def generate_key() -> str:
    """Return a fresh, URL-safe base64 Fernet key (for docs/tooling)."""
    return Fernet.generate_key().decode()


def build_cipher(key: str | None) -> Fernet:
    """Build a Fernet from a configured key, raising a clear error if unusable."""
    if not key:
        raise SecretEncryptionError(
            "SECRET_ENCRYPTION_KEY is not configured; set it to a Fernet key "
            '(generate with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())").'
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:  # malformed/short key
        raise SecretEncryptionError(
            "SECRET_ENCRYPTION_KEY is not a valid Fernet key (expected 32 "
            "url-safe base64-encoded bytes)."
        ) from exc


@lru_cache(maxsize=1)
def get_cipher() -> Fernet:
    """Return the process-wide cipher, lazily loaded from settings.

    Cached so the key is parsed once. :func:`reset_cipher_cache` clears it
    (used by tests that swap the configured key).
    """
    from app.core.settings import load_settings

    return build_cipher(load_settings().secret_encryption_key)


def reset_cipher_cache() -> None:
    """Drop the cached cipher (call after changing ``SECRET_ENCRYPTION_KEY``)."""
    get_cipher.cache_clear()


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret to a URL-safe ciphertext token."""
    return get_cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a ciphertext token produced by :func:`encrypt_secret`."""
    try:
        return get_cipher().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretEncryptionError(
            "could not decrypt secret; the stored value is corrupt or "
            "SECRET_ENCRYPTION_KEY does not match the key it was encrypted with."
        ) from exc


class EncryptedString(TypeDecorator):
    """A ``Text`` column whose value is Fernet-encrypted at rest.

    Transparent to the ORM: bind a plaintext ``str`` and read a plaintext
    ``str`` back; only the ciphertext is ever persisted. ``None`` passes
    through unchanged (for nullable columns).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return encrypt_secret(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return decrypt_secret(value)
