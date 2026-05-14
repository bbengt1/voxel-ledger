# 6. API and Interface Catalog

> **Authoritative per-endpoint reference** lives in the auto-generated companion files:
> - [openapi.json](openapi.json) — raw OpenAPI 3.1 spec
> - [api_overview.md](api_overview.md) — counts per tag (271 paths, 315 schemas, 373 operations, 46 tags)
> - [api_endpoints.md](api_endpoints.md) — every operation with params, body, responses
> - [api_schemas.md](api_schemas.md) — every component schema with fields and types
>
> This document remains the higher-level narrative catalog with conventions, auth flow, common shapes, and integration notes.

## 6.1 Conventions

- All endpoints under `/api/v1`.
- JSON over HTTPS.
- Auth: `Authorization: Bearer <jwt>` on everything except `/auth/login`, `/health`, `/api/v1/docs`, `/api/v1/redoc`, `/api/v1/openapi.json`.
- Pagination: `?limit=&offset=` (cursor pagination recommended for v2).
- Filtering: query params per resource (see [02](02_functional_requirements.md)).
- Sorting: `?sort_by=&sort_dir=` (asc/desc).
- Rate limit: 120 req/min/IP, configurable burst.
- Errors: `{ "detail": "<message>" }` with HTTP 4xx/5xx; validation errors are FastAPI's structured 422 shape.
- OpenAPI 3.1 spec served at `/api/v1/openapi.json`. The v2 SHOULD generate frontend types from this spec.

## 6.2 Endpoint Catalog (by resource)

> Endpoint paths shown without the `/api/v1` prefix. Methods: C=POST create, R=GET, U=PUT/PATCH, D=DELETE. "Full CRUD" = C, R-list, R-single, U, D.

### Authentication & Users
- `POST /auth/login` — issue JWT
- `GET /auth/me` — current user
- `PUT /auth/me/password` — change own password
- `POST /auth/register` — admin: create user
- `GET /auth/users` — admin: list users (`?is_active`)
- `GET /auth/users/{id}` — admin
- `PUT /auth/users/{id}` — admin
- `DELETE /auth/users/{id}` — admin

### Settings
- `GET /settings`
- `PUT /settings`
- `GET /settings/{key}`
- `PUT /settings/{key}`
- `PUT /settings/bulk`

### Insights (AI)
- `GET /insights/status`
- `POST /insights/summary`

### Catalog
- `/materials` — Full CRUD; `?active`, `?search`, pagination
- `/materials/{id}/receipts` — material receipts (via `/material-receipts` endpoint module)
- `/supplies` — Full CRUD; `?active`, `?category`, `?search`; `POST /supplies/{id}/adjust`
- `/rates` — Full CRUD; `?active`
- `/products` — Full CRUD; `?is_active`, `?material_id`, `?low_stock`, `?search`; max page size 500
- `/products/{id}/bom` — BOM CRUD
- `/products/{id}/locations` — per-location stock
- `/kits` — Full CRUD (kit components)
- `/custom-fields` — Full CRUD
- `/form-templates` — Full CRUD
- `/attachments` — upload/list/delete; polymorphic owner
- `/notes` — Full CRUD; polymorphic owner

### Customers
- `/customers` — Full CRUD; `?search`
- `/merge` — POST merge two customers (and other mergeable entities)

### Jobs & Production
- `/jobs` — Full CRUD; `?status`, `?material_id`, `?customer_id`, `?date_from`, `?date_to`, `?search`, `?sort_by`, `?sort_dir`
- `POST /jobs/calculate` — compute cost/price without persisting
- `/job-discovery` — list/import discovered jobs
- `/production-orders` — Full CRUD; queue management
- `/printers` — Full CRUD; `?is_active`
- `/printers/{id}/history` — history events
- `/printers/{id}/state` — current live state (from monitor)
- `/cameras` — Full CRUD; `?is_active`, `?assigned`, `?search`
- `POST /cameras/{id}/assign` — bind to printer
- `GET /cameras/{id}/snapshot` — proxied image

### Inventory
- `GET /inventory/transactions` — `?product_id`, `?material_id`, `?supply_id`, `?type`, paginated
- `POST /inventory/transactions` — create
- `GET /inventory/alerts` — low-stock
- `/inventory/locations` — Full CRUD
- `/inventory/starting-balances` — bulk seed
- `POST /inventory/transfer` — between locations

### Sales
- `/sales/channels` — Full CRUD; `?is_active`
- `/sales` — Full CRUD; `?status`, `?channel_id`, `?payment_method`, `?customer_id`, `?date_from`, `?date_to`, `?search`
- `GET /sales/metrics` — KPI tiles
- `GET /sales/{id}/shipping-label` — generate label
- `POST /sales/{id}/shipping-label/mark-printed`
- `POST /sales/{id}/refund` — partial or full
- `POST /pos/checkout` — atomic POS sale create
- `POST /pos/scan/resolve` — barcode → product
- `/settlements` — Full CRUD; statement import, line match, post payout
- `/delivery-notes` — Full CRUD

### Quotes & Invoices
- `/quotes` — Full CRUD; convert quote → sale/invoice
- `/invoices` — Full CRUD; record payment; apply credit
- `/recurring-invoices` — Full CRUD; run-now
- `/credit-notes` — Full CRUD
- `/debit-notes` — Full CRUD

### Bills, Vendors, Expenses
- `/vendors` (via accounting/expense endpoints)
- `/bills` — Full CRUD; record payment
- `/expense-claims` — Full CRUD; approve/reject
- `/billable-expenses` — Full CRUD; mark invoiced
- `/recurring-expenses` (via accounting endpoints) — Full CRUD; run-now

### Banking
- `/banking` — accounts list, balances
- `/statement-imports` — upload/list/process
- `/statement-match-rules` — Full CRUD
- `/inter-account-transfers` — Full CRUD

### Accounting Core
- `/accounting` — chart of accounts CRUD, journal entries CRUD, period open/close
- `/accounting-foundations` — initial setup / starter COA
- `/divisions` — Full CRUD
- `/budgets` — Full CRUD
- `/fixed-assets` — Full CRUD; depreciation run
- `/intangible-assets` — Full CRUD; amortization run
- `/tax` — Full CRUD profiles; remittances
- `/withholding` — Full CRUD
- `/cogs` — COGS recompute / inspect (FIFO)
- `/approvals` — Full CRUD; approve/reject
- `/audit` — read-only audit log query

### Reports & Dashboard
- `GET /reports/inventory` (+ CSV)
- `GET /reports/sales` (+ CSV) — `?period`
- `GET /reports/pl` (+ CSV)
- `GET /reports/balance-sheet`
- `GET /reports/cash-flow`
- `GET /reports/trial-balance`
- `GET /reports/ar-aging`
- `GET /reports/ap-aging`
- `GET /reports/sales-tax-liability`
- `GET /dashboard/summary`
- `GET /dashboard/charts/revenue`
- `GET /dashboard/charts/materials`
- `GET /dashboard/charts/profit-margins`

### Misc
- `/locations` — Full CRUD (general locations)
- `/orders` — alias / wrapper for sales orders
- `/email` — send-email actions, delivery log
- `/batch-ops` — bulk edit/archive/delete with preview
- `/sales-channels` (legacy alias to /sales/channels)
- `/inventory-starting-balances` — bulk seed
- `GET /health` — outside `/api/v1`

## 6.3 Authentication Flow

```
POST /api/v1/auth/login { email, password }
  → 200 { access_token, token_type: "bearer", user }
  → 401 { detail: "Invalid credentials" }

All other requests:
  Authorization: Bearer <jwt>
  → 401 { detail: "Not authenticated" }     # missing/invalid
  → 403 { detail: "Admin required" }        # role gate
```

The frontend's axios interceptor catches 401, clears Zustand auth state, and redirects to `/login` preserving the originally requested URL.

## 6.4 Common Response Shapes

```jsonc
// List
{
  "items": [ /* resource */ ],
  "total": 1234,
  "limit": 50,
  "offset": 0
}

// Single resource
{ /* resource fields, including id, created_at, updated_at */ }

// Error (FastAPI default)
{ "detail": "Human readable message" }

// Validation error (FastAPI 422)
{ "detail": [{ "loc": ["body","field"], "msg": "...", "type": "..." }] }
```

## 6.5 File Import / Export Formats

| Surface | Direction | Format | Notes |
|---|---|---|---|
| Inventory report | Export | CSV | columns: sku, name, on_hand, unit_cost, value |
| Sales report | Export | CSV | columns per period bucket |
| P&L report | Export | CSV | row per account |
| Bank statement | Import | CSV / OFX | column mapping via `bank_import_mapping` |
| Marketplace settlement | Import | CSV | per-channel format; lines matched to sales |
| Attachments | Upload | multipart/form-data | any mime; stored under `/srv/3d-print-sales/data/attachments` |
| Product label | Export | PDF / PNG (per request) | barcode + SKU |
| Shipping label | Export | PDF | sale-derived |
| Quote / Invoice | Export | PDF | also delivered via email |

## 6.6 Webhooks / Callbacks (v2)

**Outbound** — user-configured destinations subscribe to event types from the domain event log. Each delivery includes:
- Headers: `X-Event-Id`, `X-Event-Type`, `X-Event-Position`, `X-Signature` (HMAC-SHA256 of body with per-target secret), `X-Timestamp`.
- Body: the event payload + envelope (`{ id, type, occurred_at, payload }`).
- Retries: exponential backoff up to 24 h; permanent failures land in a dead-letter view.

Initial event types exposed:
- `sale.created`, `sale.confirmed`, `sale.refunded`, `sale.shipped`
- `invoice.issued`, `invoice.paid`, `invoice.overdue`
- `quote.sent`, `quote.accepted`
- `printer.state_changed`, `printer.failed`, `printer.completed`
- `inventory.low_stock`, `material.received`
- `settlement.imported`, `settlement.posted`
- `period.closed`

Endpoints:
- `POST /webhooks/outbound` — create subscription `{ url, secret, event_types[], active }`
- `GET /webhooks/outbound` — list
- `PATCH /webhooks/outbound/{id}`, `DELETE /webhooks/outbound/{id}`
- `GET /webhooks/outbound/{id}/deliveries` — delivery log + status
- `POST /webhooks/outbound/{id}/deliveries/{delivery_id}/retry` — manual retry

**Inbound** — per-integration receivers, signature-verified:
- `POST /webhooks/inbound/carrier/{provider}` — carrier tracking updates (EasyPost/ShipStation)
- `POST /webhooks/inbound/marketplace/{channel_slug}` — marketplace order/refund events (where the channel offers webhooks)

## 6.7 Internal Service-to-Service Contracts

There are no separate internal services today; everything runs in one FastAPI process. The conceptual contracts that **would** need to become RPCs if split:

- `cost_calculator.compute(job_inputs) -> cost_breakdown`
- `reference_number_service.next("sale" | "invoice" | "quote", year) -> string`
- `inventory_service.post(transaction) -> ledger_entry + accounting_postings`
- `cogs_fifo_service.lookup(product_id, qty, at) -> unit_cost`
- `accounting_service.post(journal_entry) -> entry_id`
- `printer_monitoring.state(printer_id) -> snapshot`
- `email_service.send(template, recipient, attachments) -> delivery_id`

## 6.8 Message / Queue Formats

No external broker today. If v2 introduces one, candidate topics:
- `inventory.transaction.posted`
- `sale.confirmed` / `sale.refunded`
- `invoice.issued` / `invoice.paid`
- `printer.state_changed`
- `settlement.imported`
