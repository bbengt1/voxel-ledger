# API

High-level catalogue. The authoritative reference is the live OpenAPI doc at **`/docs`** on a running backend (Swagger UI) or **`/openapi.json`** (raw spec). This file points at the non-obvious patterns.

## 1. Auth

- `POST /api/v1/auth/login` — email + password → access (JWT, 15min) + refresh (rotating, 30d).
- `POST /api/v1/auth/refresh` — exchange refresh for new pair. Reuse detection revokes the family.
- `POST /api/v1/auth/logout` — revoke current refresh-token family.
- `GET /api/v1/auth/me` — current user + role.

Every other endpoint expects `Authorization: Bearer <access>`. Roles: `owner`, `bookkeeper`, `production`, `sales`, `viewer`. Endpoints declare their accepted roles via `Depends(require_role(...))`.

## 2. Bounded contexts

| Context | Prefix | Key endpoints |
| --- | --- | --- |
| Accounts (CoA) | `/api/v1/accounts` | CRUD, tree view |
| Journal entries | `/api/v1/journal-entries` | Manual JEs (approval-gated above threshold) |
| Accounting periods | `/api/v1/accounting-periods` | open / close / lock state machine |
| Sales | `/api/v1/sales`, `/api/v1/pos`, `/api/v1/refunds` | Draft → confirm → fulfill |
| Invoices | `/api/v1/invoices` | Send, mark void, late-fee |
| Bills | `/api/v1/bills`, `/api/v1/bill-payments` | AP lifecycle |
| Banking | `/api/v1/banking/*` | Imports, mapping, reconciliation, transfers |
| Fixed assets | `/api/v1/fixed-assets`, `/api/v1/depreciation-runs` | Schedule + run |
| Tax | `/api/v1/tax-profiles`, `/api/v1/tax-remittances`, `/api/v1/withholding-profiles` | Profile + remittance + 1099 |
| Settlements | `/api/v1/settlements` | Marketplace imports + payout JE |
| Reports | `/api/v1/reports/*` | P&L, BS, CF, TB, sales-by-period, inventory valuation, AR/AP aging |
| Dashboard | `/api/v1/dashboard/*` | KPIs + AI insights |
| Control Center | `/api/v1/control-center` | Admin aggregate |
| Webhooks (out) | `/api/v1/webhooks/*` | Subscriptions, deliveries, replay |
| Webhooks (in)  | `/api/v1/webhooks/inbound/*` | Carrier + marketplace intake |
| Batch ops | `/api/v1/batch/{preview,commit}` | Bulk archive / mark-void |
| Settings | `/api/v1/settings/*` | Typed key/value |

## 3. Non-obvious patterns

### Settings are typed
Settings live under `app/services/settings/schemas.py`. Each tunable subclasses `SettingSchema` with a `key`, `default`, and a Pydantic `value` field. The HTTP API enforces the registered shape; an unknown key returns 400.

When adding a new tunable: register a schema. Don't write raw rows.

### Event store + projections
Accounting-affecting mutations call `event_store.append(EventCreate(...), session=session)`. The append:
1. Validates the payload against the registered Pydantic model.
2. Takes a per-transaction advisory lock so two writers can't race on `prev_event_hash`.
3. Allocates the next `position`, computes the SHA-256 chain hash.
4. Fans out to every registered projection handler (audit log, balance, inventory-on-hand, ...) in the same transaction.

Projections must be idempotent — replay rebuilds them from `position=0`. See `app/projections/` for examples.

### Reference numbering
`{PREFIX}-{YYYY}-{NNNN}` (e.g. `INV-2026-0042`). Allocated by a DB sequence inside the originating transaction, never by `COUNT(*)`. See `app/services/reference.py`.

### Webhooks: outbound signing
Outbound deliveries sign the canonical JSON body with HMAC-SHA256 under the per-subscription secret. The signature lives in `X-Vl-Signature: sha256=<hex>`. Subscribers verify by recomputing over the raw body with the secret you gave them at create-time (returned once; rotate via `PATCH /subscriptions/{id}` with `rotate_secret=true`).

### Webhooks: inbound idempotency
Every inbound POST dedupes on `(provider, external_event_id)` via `webhook_inbound_event`. Re-POSTing the same event returns `200` + `status='duplicate'` without re-applying. Signature verification is per-provider — the shared secret is configured in Settings (`webhooks.inbound.<kind>.<provider>.secret`).

### Approval gating
Threshold-gated mutations (e.g. JE above limit, refund above limit) create an `approval_request` row instead of applying. The owner approves or rejects via `/api/v1/approvals`. The original action consumes the approval on apply.

### CSV exports
All report endpoints accept `?format=csv` and stream a CSV body with `Content-Type: text/csv`. The frontend wires this through `URL.createObjectURL` + an anchor click — see `frontend/src/pages/reports/*.tsx` for the pattern.

### Pagination
List endpoints default to `limit=50`. Cursor pagination on hot lists (sales, inventory transactions, audit log) via opaque `cursor` query param. Stable ordering is enforced server-side.

### Errors
- `400` — validation / domain-rule violation. Body: `{detail: "<message>"}`.
- `401` — missing / invalid / expired JWT.
- `403` — role not allowed.
- `404` — resource not found, or unknown provider on inbound webhooks.
- `409` — state-machine conflict (e.g. confirming an already-confirmed sale).
- `422` — Pydantic body validation.

## 4. Codegen drift

Frontend types live in `frontend/src/api/types.ts`, generated from `backend/app/main.py`'s OpenAPI surface. The build runs codegen as a prebuild step; CI fails on drift. If you change a router signature or schema, regenerate:

```bash
VOXEL_LEDGER_PYTHON=.venv/bin/python ./scripts/export-openapi.sh
cd frontend && pnpm run codegen
```

## 5. Versioning

The API is unversioned beyond `/api/v1/`. Breaking changes require a `/api/v2/` mount, a deprecation banner on `v1`, and a documented sunset window. None planned today.
