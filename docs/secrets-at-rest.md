# Secrets at rest

This is the project standard for storing sensitive third-party secrets in the
database. It was introduced as the epic #312 (QuickBooks Online) hardening
follow-up to Phase 1 (#314), which initially stored the QBO OAuth tokens in
plaintext columns.

## TL;DR

- Encrypt sensitive DB columns with **Fernet** (authenticated AES-128-CBC +
  HMAC-SHA256) via the helper in [`backend/app/core/crypto.py`](../backend/app/core/crypto.py).
- The key is config-driven: `SECRET_ENCRYPTION_KEY` (env) →
  `Settings.secret_encryption_key`, validated against the placeholder denylist
  like every other secret.
- For new columns, use the `EncryptedString` SQLAlchemy type — it encrypts on
  write and decrypts on read, so model/service code keeps working with plain
  `str` values.

## Generating a key

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the result in `SECRET_ENCRYPTION_KEY` in your env file (see
`.env.dev.example`, `.env.prod.example`, `.env.web02.example`). The value is a
32-byte url-safe base64 key.

**Keep the key stable.** Rotating `SECRET_ENCRYPTION_KEY` makes every
previously-encrypted value undecryptable — reads raise `SecretEncryptionError`.
For the QBO tokens the recovery path is simply to **disconnect and reconnect**
QuickBooks, which writes fresh tokens under the new key. There is no key-rotation
re-encryption tooling yet; add one before adopting this for data that can't be
trivially re-created.

## Using it for a new column

```python
from app.core.crypto import EncryptedString

class MyModel(Base):
    api_key: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
```

The underlying SQL type is `Text`, so adopting (or dropping) encryption on an
existing column is a **data** migration, not a schema one — re-encrypt or
decrypt the existing rows in place. See
[`backend/alembic/versions/0079_encrypt_oauth_tokens.py`](../backend/alembic/versions/0079_encrypt_oauth_tokens.py)
for the pattern (and its reversible `downgrade`).

If a value should only ever be set programmatically and never read back as
plaintext at all, prefer a one-way hash instead — `EncryptedString` is for
secrets the app must use (tokens, API keys, passwords for outbound auth).

## Defense in depth

Encryption at rest is **in addition to**, not a replacement for, the existing
guarantee that these secrets are never serialized into API responses, events,
or logs (e.g.
`test_admin_quickbooks_oauth.py::test_status_connected_never_leaks_tokens`).
Keep both: redact at the response/event/log layer, and encrypt in the column.

## Current adoption

| Secret | Storage | Encrypted? |
| --- | --- | --- |
| `oauth_credential.access_token` / `refresh_token` (QBO) | `EncryptedString` | ✅ yes |
| `email.smtp_password_secret` | plaintext setting | ⬜ candidate to migrate |
| `camera.password_secret` | plaintext setting | ⬜ candidate to migrate |
| `moonraker_api_key` | plaintext setting | ⬜ candidate to migrate |

The three remaining plaintext secrets live in the generic `setting` table
(rather than dedicated columns) and are lower-sensitivity (LAN-local device
credentials). Migrating them onto this helper — which means encrypting the
relevant `setting.value` rows behind a settings-layer hook — is a tracked
follow-up and can be a separate PR.
