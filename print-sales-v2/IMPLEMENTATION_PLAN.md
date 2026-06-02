# Print-Sales v2 — Implementation Plan

A phased plan for building a new application from the specifications in [print-sales-v2/](.). Optimized for a single small-team build targeting a single-tenant deployment on one Linux VM, with PostgreSQL 16 and a stateless FastAPI + React stack.

---

## 1. Goals and Non-Goals

**Goals**
- Replace v1 spreadsheet + ad-hoc tooling with one source of truth covering catalog, inventory, production, sales, AR/AP, banking, accounting, and reporting.
- Make accounting **event-sourced**: domain events are authoritative; journal entries, balances, and reports are projections.
- Eliminate type drift: frontend client and types are **generated** from the backend OpenAPI 3.1 spec at build time; CI fails on drift.
- Hit operator-grade performance: cost-calc < 200 ms, POS scan-to-line < 500 ms, list views < 400 ms.
- Maintain durable accounting: every business mutation posts to the event log inside the same DB transaction as the side effect (inventory, ledger).

**Non-goals (v2)**
- Multi-currency, multi-tenant, multi-org.
- MFA / SSO.
- Staging environment (testing is local + production).
- S3-backed attachments (local disk + offsite rsync).
- PCI scope (no card processing in-house).
- Heavy job-broker infra (prefer Postgres-native queue: pg-boss / pgmq / Arq).

---

## 2. Architecture Snapshot

```
┌────────────────────────────────────────────────────────────────────┐
│  Browser (React 19 / Vite / TS / Tailwind 4 / Radix / TanStack Q)  │
└─────────────┬──────────────────────────────────────────────────────┘
              │ HTTPS, JWT bearer
┌─────────────▼──────────────────────────────────────────────────────┐
│  nginx (TLS termination, static assets, reverse proxy)             │
└─────────────┬──────────────────────────────────────────────────────┘
              │
┌─────────────▼──────────────────────────────────────────────────────┐
│  FastAPI app (Uvicorn)                                             │
│  ├── routers (thin)                                                │
│  ├── services (business logic, ~12 bounded contexts)               │
│  ├── event store (append-only, hash-chained)                       │
│  ├── projection engine (sync read-model updates)                   │
│  └── integrations: Moonraker WS, SMTP, EasyPost/ShipStation        │
└─────┬──────────────────┬───────────────────────────┬───────────────┘
      │                  │                           │
┌─────▼─────┐    ┌───────▼────────┐         ┌────────▼──────────┐
│ Postgres  │    │ PG-native      │         │ Local disk        │
│ 16 (events│    │ job queue      │         │ /srv/.../         │
│ + reads)  │    │ (pg-boss/pgmq) │         │ attachments       │
└───────────┘    └────────────────┘         └───────────────────┘
```

Bounded contexts (organize code by these, not by technical layer): **Identity & Access, Catalog, Inventory, Production, Sales, AR, AP, Banking, Accounting, Reporting, Notifications, Platform**.

---

## 3. Technology Decisions

| Concern | Choice | Notes |
|---|---|---|
| Backend framework | FastAPI + Uvicorn | Async; OpenAPI 3.1 native |
| ORM | SQLAlchemy 2 async | Async-first; v1 parity |
| Database | PostgreSQL 16 | Single prod DB; SQLite for unit tests only |
| Migrations | Alembic | Enforced on every deploy; safe-to-rerun |
| Job queue | pg-boss (Node) or pgmq + Arq | Postgres-native; no Redis/Rabbit |
| Frontend | React 19 + Vite + TS | SPA |
| Styling | Tailwind 4 + Radix UI | Dense, accessible |
| Server state | TanStack Query 5 | Stale-time tuned per endpoint |
| Client state | Zustand 5 | Auth, POS cart |
| Forms | react-hook-form + zod | Shared validation contract |
| Client codegen | `openapi-typescript` | Prebuild step; CI drift check |
| Auth | JWT access (~15 m) + rotating refresh (~30 d) | Per-family revocation |
| Email | SMTP, retryable | Delivery log persisted |
| Shipping | EasyPost **or** ShipStation (pick one) | Static-label fallback retained |
| Printer integration | Moonraker WebSocket | **Lazy-loaded**, not a startup dep |
| Hosting | Docker Compose on `web01.internal` | systemd unit; n8n deploy workflow |

---

## 4. Cross-Cutting Foundations (Build First)

These are prerequisites for every feature and must land before bounded-context work begins.

### 4.1 Event log
- Append-only table: `id`, `position` (monotonic bigserial), `type`, `aggregate_id`, `payload` (jsonb), `occurred_at`, `recorded_at`, `actor_user_id`, `correlation_id`, `causation_id`, `prev_event_hash` (sha256 of previous row), `schema_version`.
- All writes go through a single `EventStore.append(event)` API that runs inside the caller's transaction.
- Hash chain verified on demand by a `verify_chain` admin endpoint.
- `schema_version` enables upcasters when payload shapes evolve.

### 4.2 Projection engine
- Synchronous projection on commit: each event type has registered handlers that mutate read-model tables (`journal_line`, `product_location_stock`, `invoice`, etc.) in the **same transaction**.
- Rebuild path: drop projection tables → replay events in `position` order → snapshot every N events for fast replay.

### 4.3 Reference number allocator
- Table `reference_sequence(prefix, year, last_value)`.
- Allocation uses `UPDATE ... RETURNING` (row lock) — **never** `COUNT(*)`. Format `{PREFIX}-{YYYY}-{NNNN}`.

### 4.4 Auth & RBAC
- Roles: `owner`, `bookkeeper`, `production`, `sales`, `viewer`. Deny-by-default permission matrix.
- Refresh-token family revocation: any reuse of a rotated token invalidates the family.
- All endpoints require bearer except `/auth/login`, `/health`, `/api/v1/docs`, `/api/v1/openapi.json`.

### 4.5 Audit log
- Projection from event log; query API for accounting compliance.
- Captures: actor, before/after (where applicable), timestamp, IP.

### 4.6 OpenAPI → frontend types
- Backend exports spec at `/api/v1/openapi.json`.
- Frontend `prebuild` script: `openapi-typescript` generates `src/api/types.ts` + a thin fetch client.
- CI step: regenerate and `git diff --exit-code` to fail on drift.

### 4.7 Settings service
- Key-value with typed schema and safe defaults for all cost-engine inputs (labor rate, machine rate, overhead %, power cost, margin %).
- Bulk-update endpoint.

### 4.8 Polymorphic refs
- `entity_kind` + `entity_id` columns on `inventory_transaction`, `attachment`, `note`, `audit_log`. Indexed composite.

---

## 5. Phased Roadmap

Each phase ends with a deployable slice. Frontend pages ship alongside their backend endpoints.

### Phase 0 — Project bootstrap (1 week)
- Monorepo layout (`backend/`, `frontend/`, `ops/`, `docs/`).
- Docker Compose dev + prod targets.
- Alembic baseline, CI (lint, type-check, test, codegen-drift), pre-commit hooks.
- Auth scaffolding, `/health`, OpenAPI publishing, frontend codegen pipeline.
- Login page, protected-route shell, theme toggle.

### Phase 1 — Foundations (2 weeks)
- Event log + projection engine + hash chain + replay tooling.
- Reference sequences.
- Audit log query.
- Settings service.
- Users & roles admin pages.
- **Exit criteria:** can append a `TestEvent`, project it to a dummy read model, query the audit log, verify hash chain.

### Phase 2 — Catalog (2 weeks)
- Materials (with `material_receipt` and weighted-average costing).
- Supplies, rates.
- Products with auto-SKU + optional UPC.
- BOM rows with polymorphic component (material / supply / product); cycle detection; cost rollup.
- Custom fields, form templates, attachments, notes.
- Frontend: list + detail pages for each; product detail with live cost preview from cost engine.

### Phase 3 — Inventory ledger (1 week)
- `inventory_transaction` write API (production, sale, adjustment, return, waste, receipt, transfer).
- `product_location_stock` projection (cached on-hand per location).
- Low-stock alerts endpoint.
- Frontend: transactions list, alerts view, starting balances form.

### Phase 4 — Accounting core (2 weeks)
- Chart of accounts (hierarchical).
- Journal entries (debit/credit) — write path goes through events.
- Period open/close/lock as events.
- Divisions, budgets per account.
- Approval requests + workflow.
- Frontend: COA tree, journal entry form, period management.

### Phase 5 — Jobs & production (2 weeks)
- Job CRUD, plates, multi-printer assignment, `pieces = min(parts per set)`.
- `POST /jobs/calculate` live cost endpoint (< 200 ms; pure function over inputs + rates + materials).
- Printers CRUD; Moonraker WebSocket integration (**lazy-loaded**, monitor module starts on demand).
- Cameras (1:1 with printer); backend snapshot proxy — never expose credentials.
- Printer history events.
- Production orders, job discovery import.
- Frontend: job form with live cost panel; printer monitor grid; production order queue.

### Phase 6 — Sales pathway (3 weeks)
- Sales channels with fee model.
- Sales CRUD; `sale_item` lines (product or job); reference allocator for sale numbers.
- COGS FIFO service.
- Posts inventory transactions + journal entries in same TX (via events).
- POS module (barcode scan, cart, checkout) — keyboard-first, < 500 ms scan-to-line.
- Refunds with approval workflow over threshold.
- Shipping labels via carrier + static fallback.
- Frontend: sales list/detail, POS screen, refund flow, shipping label print.

### Phase 7 — AR (1.5 weeks)
- Quotes, invoices (with auto-allocated reference numbers).
- Payments, customer credits, credit/debit notes.
- Recurring invoices (worker job).
- Late fees (worker job).
- AR aging report.
- Email delivery for quotes/invoices with delivery log + retry.
- Frontend: invoice form, payment recording, statement send, AR aging.

### Phase 8 — AP & Banking (2 weeks)
- Vendors, bills, bill payments, recurring bills.
- Expense categories, expense claims, billable expenses.
- Bank import mappings (CSV/OFX) — user-defined column maps.
- Statement imports, match rules, reconciliation.
- Inter-account transfers.
- Frontend: vendor list, bill form, banking reconciliation UI.

### Phase 9 — Specialized accounting (1.5 weeks)
- Fixed assets, intangible assets.
- Depreciation/amortization runs (worker jobs).
- Tax profiles (compound, reverse-charge) and remittances.
- Withholding profiles.
- Marketplace settlement reconciliation with auto-match.
- Frontend: asset register, depreciation schedule, tax profile config, settlement matcher.

### Phase 10 — Reporting & Dashboards (1.5 weeks)
- P&L, Balance Sheet, Cash Flow, Trial Balance.
- AR/AP aging, sales-tax liability, inventory, sales-by-period.
- CSV export on every report.
- Dashboard KPI tiles + charts (recharts).
- AI insights summary (low-margin SKUs, sales trends) — async background.
- Frontend: report pages, dashboard.

### Phase 11 — Notifications & Extensions (1 week)
- Outbound webhooks: subscription CRUD, HMAC-SHA256 signing, retry with exponential backoff, DLQ.
- Inbound webhooks: carrier tracking, marketplace orders/refunds.
- Batch operations (bulk edit/archive/delete with preview).
- Control Center (pending approvals, low stock, overdue invoices, failed jobs, WS health).

### Phase 12 — Hardening & cutover (1.5 weeks)
- Load test the perf budgets.
- Backup + PITR drill (RPO ≤ 24 h, RTO ≤ 2 h).
- WCAG 2.1 AA pass on primary flows.
- Data migration from v1 (one-shot script per bounded context; events backfilled with `schema_version=0`).
- Documentation pass.

**Total: ~21 weeks** for a small team; parallelizable where dependencies allow (frontend often trails backend by half a phase).

---

## 6. Performance, Reliability, Security Targets

| Target | Budget | How it's met |
|---|---|---|
| API p95 (simple GET) | < 200 ms | Index-covered queries; no N+1; TanStack Query caches |
| List endpoints (≤ 500 rows) | < 400 ms | Pagination defaults limit=50; cursor pagination on hot lists |
| Cost-calc | < 200 ms | Pure-function service; no DB writes |
| POS scan → line | < 500 ms | Indexed UPC/SKU lookup; optimistic UI |
| Printer freshness | < 5 s | Moonraker WS push; in-memory state cache |
| FCP / TTI | < 1.5 s / 2.5 s | Vite code-split; route-level lazy load |
| Uptime | 99.5% | Off-hours maintenance acceptable |
| RPO / RTO | 24 h / 2 h | Nightly PG dump + WAL archive; tested restore |
| Rate limit | 120 req/min/IP | nginx or FastAPI middleware |

Security non-negotiables: bcrypt; secrets via env file with startup validation (no placeholders); CORS allow-list; audit log on every accounting mutation; approval gate above thresholds; camera creds never client-side.

---

## 7. Testing Strategy

- **Unit (pytest)**: every service module. Target 80% coverage on services.
- **Integration (pytest + ephemeral Postgres)**: every endpoint group with auth + role matrix.
- **Property tests (Hypothesis)** for: BOM rollup, COGS FIFO, reference allocator under concurrency, pieces-min formula, depreciation schedules.
- **Replay test**: nightly rebuild of projections from event log; assert read-model parity.
- **Frontend**: Vitest unit + a small Playwright suite covering login, POS checkout, job creation, invoice send.
- **Codegen drift**: CI regenerates and diffs `frontend/src/api/types.ts`.
- **Migration tests**: every Alembic revision must be safe-to-rerun on a populated DB.

---

## 8. Operational Model

- **Single VM** (`web01.internal`), Docker Compose, systemd unit, nginx fronting.
- **Deploys**: n8n workflow (pull → migrate → rebuild → verify). Migrations are mandatory; skipping crashes startup by design.
- **Backups**: nightly `pg_dump` + continuous WAL archive to offsite. Attachments rsynced nightly.
- **Observability**: structured JSON logs with request id; `/health` endpoint; per-request timing; worker exposes last-run + last-success; OpenTelemetry traces (P1 stretch).
- **Single environment**: no staging. Compensate with feature flags + cautious deploys + tested rollback.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Event log becomes a hotspot under write load | High | bigserial PK; partition by month if `position` exceeds tens of millions; snapshot projections |
| Projection drift from events | High | Idempotent handlers; nightly replay test; verify hash chain in admin tool |
| Moonraker dependency crashes startup | Med | Lazy-load monitor; never block app boot on WS connect |
| Reference allocator races | High | Use row-locked sequence, not COUNT — covered in property tests |
| Frontend type drift | Med | Codegen + CI drift check |
| Single-VM hardware failure | Med | Tested PITR restore; documented runbook |
| Carrier vendor lock-in | Low | Static-label fallback retained; carrier behind a thin adapter |
| Scope creep into v1 features | Med | Honor explicit v2 won't-do list (multi-currency, MFA, S3, staging) |

---

## 10. Open Questions (resolve before Phase 4)

- Exact approval thresholds for refunds/adjustments/period-close — owner decision needed.
- Carrier choice: EasyPost vs ShipStation.
- Worker library: pg-boss vs Arq+pgmq — pick after a 1-day spike comparing operability.
- Whether to migrate v1 historical data or start fresh with opening balances as a single event.
- Dashboard "AI insights" provider/scope — defer to Phase 10 spike.

---

*Plan derived from specs in [01_system_overview.md](01_system_overview.md) through [12_glossary_assumptions_decisions.md](12_glossary_assumptions_decisions.md) and the API surface in [api_overview.md](api_overview.md).*
