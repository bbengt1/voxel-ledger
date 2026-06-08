"""Secret-at-rest encryption (app/core/crypto.py) — epic #312 hardening.

Covers the round-trip helper, key validation/failure modes, and — the headline
guarantee — that QBO OAuth tokens are stored as ciphertext in the DB while the
ORM still hands plaintext back to the service layer.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from app.core import crypto
from app.models import Base
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --------------------------------------------------------------------------- #
# helper: round-trip + key handling
# --------------------------------------------------------------------------- #
def test_encrypt_decrypt_round_trip() -> None:
    secret = "supersecret-access-token"
    token = crypto.encrypt_secret(secret)
    assert token != secret  # actually transformed
    assert crypto.decrypt_secret(token) == secret


def test_ciphertext_is_non_deterministic() -> None:
    # Fernet embeds a random IV + timestamp, so two encryptions differ but both
    # decrypt back to the same plaintext.
    a = crypto.encrypt_secret("same")
    b = crypto.encrypt_secret("same")
    assert a != b
    assert crypto.decrypt_secret(a) == crypto.decrypt_secret(b) == "same"


def test_generate_key_is_usable() -> None:
    key = crypto.generate_key()
    cipher = crypto.build_cipher(key)
    assert cipher.decrypt(cipher.encrypt(b"x")) == b"x"


@pytest.mark.parametrize("missing", [None, ""])
def test_build_cipher_missing_key_raises(missing: str | None) -> None:
    with pytest.raises(crypto.SecretEncryptionError, match="not configured"):
        crypto.build_cipher(missing)


def test_build_cipher_invalid_key_raises() -> None:
    with pytest.raises(crypto.SecretEncryptionError, match="not a valid Fernet key"):
        crypto.build_cipher("not-a-real-fernet-key")


def test_decrypt_with_wrong_key_raises() -> None:
    # Encrypt under a different key, then try to decrypt with the process key.
    other = Fernet(Fernet.generate_key())
    foreign = other.encrypt(b"secret").decode("ascii")
    with pytest.raises(crypto.SecretEncryptionError, match="could not decrypt"):
        crypto.decrypt_secret(foreign)


def test_decrypt_of_plaintext_raises() -> None:
    # A legacy/unmigrated plaintext value is not valid ciphertext.
    with pytest.raises(crypto.SecretEncryptionError):
        crypto.decrypt_secret("supersecret-access-token")


# --------------------------------------------------------------------------- #
# TypeDecorator: ciphertext at rest, plaintext through the ORM
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_oauth_tokens_stored_as_ciphertext(session: AsyncSession, schema: None) -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    cred = OAuthCredential(
        provider=OAuthProvider.QUICKBOOKS.value,
        realm_id="4620816365",
        access_token="supersecret-access-token",
        refresh_token="supersecret-refresh-token",
        access_token_expires_at=now + timedelta(hours=1),
        refresh_token_expires_at=now + timedelta(days=100),
    )
    session.add(cred)
    await session.commit()

    # Raw column value (bypassing the TypeDecorator) must be ciphertext.
    raw = (
        await session.execute(text("SELECT access_token, refresh_token FROM oauth_credential"))
    ).one()
    assert "supersecret" not in raw.access_token
    assert "supersecret" not in raw.refresh_token
    # And it must be our ciphertext: decrypts back to the original plaintext.
    assert crypto.decrypt_secret(raw.access_token) == "supersecret-access-token"
    assert crypto.decrypt_secret(raw.refresh_token) == "supersecret-refresh-token"

    # Reading through the ORM transparently decrypts.
    session.expire_all()
    loaded = (await session.execute(select(OAuthCredential))).scalar_one()
    assert loaded.access_token == "supersecret-access-token"
    assert loaded.refresh_token == "supersecret-refresh-token"
