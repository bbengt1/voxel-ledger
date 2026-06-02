# Voxel Ledger

**A production accounting + operations platform for a real 3D-printing business** — double-entry accounting, inventory, manufacturing, and point-of-sale in one event-sourced system.

🔗 **Live:** [print.bengtsonprecision3d.com](https://print.bengtsonprecision3d.com/) &nbsp;·&nbsp; FastAPI + Postgres backend, React 19 frontend, deployed via Docker Compose.

> Built and operated for **Bengtson Precision 3D**. This repo is shared publicly as a work sample — it's a single-tenant app running live in production, not a toy demo.

---

## Why it's worth a look

This isn't a CRUD tutorial. It's a real business system with the kind of depth you only get from running your own books and shop floor:

- **Event-sourced ledger.** Domain events are the source of truth; journal entries, account balances, inventory on-hand, and costs are all **projections** rebuilt from an append-only, hash-chained event log. Read models can be replayed from scratch.
- **Double-entry accounting done properly** — chart of accounts, journal entries, accounting periods, fixed assets + depreciation, tax profiles, and withholding — wired to the operational side so a sale or a build posts the right GL entries automatically.
- **A manufacturing model, not just a catalog.** Materials → **Parts** (printed, FIFO-costed, stockable) → **Products** (assembled from parts + supplies + labor). Jobs produce parts; **Builds** consume parts/supplies into finished goods. Cost rolls up the whole tree.
- **A real, reversible data migration shipped to production.** The Parts model was retrofitted onto live data via a dry-run-first, idempotent, reconciled backfill with a documented cutover + rollback — executed against production with zero data loss. (See the case study below.)
- **Type-safe end to end.** The frontend's API types are **generated from the backend's OpenAPI schema** at build time; CI fails on drift. No hand-written, drifting client types.

## By the numbers

| | |
|---|---|
| **70** versioned REST API modules | **389** backend test modules (pytest) |
| **76** Alembic migrations | **135** frontend pages (Vitest-tested) |
| **8** event-sourced projections | **5** RBAC roles, deny-by-default |

## Tech stack

**Backend** — Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Alembic · PostgreSQL 16 (`asyncpg`). Postgres-native throughout — no Redis/RabbitMQ; the event store + projections live in the same DB and commit atomically.

**Frontend** — React 19 · TypeScript 5.6 · Vite · Tailwind 4 · Radix UI · TanStack Query · Zustand · Recharts. API types generated from OpenAPI.

**Ops** — Docker Compose on a single VM, nginx, fronted by a Cloudflare Tunnel; n8n-orchestrated deploy (pull → migrate → rebuild → verify) with health-gated rollout.

## What it does

A full back-office for a manufacturing business, organized into bounded contexts:

| Domain | Capabilities |
|---|---|
| **Accounting** | Chart of accounts, journal entries, accounting periods, fixed assets + depreciation, tax profiles, withholding |
| **Accounts receivable** | Invoices, recurring invoices, late-fee policies, payments, credit/debit notes, customer credit |
| **Accounts payable** | Bills, bill payments, vendors, expense claims, billable expenses |
| **Banking** | Statement imports, reconciliation, match rules, inter-account transfers, deposit slips |
| **Inventory** | Locations, transaction ledger, on-hand projection, low-stock alerts, valuation, FIFO COGS |
| **Catalog** | Materials, supplies, **parts**, products, polymorphic bill-of-materials |
| **Production** | Printers (Moonraker), jobs + plates, production orders, **builds/assembly**, a live cost engine |
| **Sales** | Sales channels, orders, point-of-sale, quotes, shipments, refunds, settlements |
| **Platform** | RBAC auth, reporting + dashboards, saved reports, webhooks (in/out), custom fields, full-text search, approval workflows, audit log |

## Architecture highlights

- **Append-only event log** with a hash chain; every state change is an event. A `@projection` registry maps event types to read-model updaters that run **synchronously inside the same transaction** as the append — so reads are consistent immediately, and any read model can be rebuilt by replay.
- **FIFO cost-of-goods** for products and parts, with a cost engine that values jobs, parts, and builds (materials + labor + machine + overhead + failure buffer) in `Decimal` money.
- **Race-safe reference numbering** (`{PREFIX}-{YYYY}-{NNNN}`) via an atomic DB-sequence allocator — never `COUNT(*)`.
- **RBAC** with fixed roles (`owner` / `bookkeeper` / `production` / `sales` / `viewer`), deny-by-default at every endpoint.
- **OpenAPI-driven** frontend: `openapi.json` → generated TypeScript types at prebuild; drift fails CI.

## Case study — retrofitting a manufacturing model onto live data

The system originally tied jobs directly to products. A multi-phase epic introduced a proper **assembly line** (Materials → Parts → Products; jobs produce parts; builds assemble products) — across backend, frontend, inventory, and cost/COGS — and then **migrated the live production database onto it**:

- An **in-place, dry-run-first, idempotent, reversible** backfill engine (derive deduped parts from historical print recipes → build product BOMs → re-point open jobs), modeled on the existing migration framework.
- A **reconciliation gate**: on-hand parity is a hard invariant (the backfill writes no inventory rows), cost moves are surfaced for sign-off — the cutover aborts on any hard failure.
- A documented **runbook**: backup → rehearse on a restored snapshot until clean → maintenance-window cutover → scripted rollback.
- The cutover ran against production and **reconciled clean (0 hard failures, on-hand parity held)**; legacy code paths were then retired.

Every phase shipped incrementally behind tests and review. It's a good window into how I approach large, risky changes to systems that can't afford downtime or data loss.

## Quick start

```bash
git clone <this-repo>
cd voxel-ledger
make bootstrap
```

`make bootstrap` checks your toolchain, generates a local `.env.dev`, builds the dev stack, applies migrations, and seeds an owner. Then:

- **Frontend** — http://localhost:5173
- **Backend** — http://localhost:8000 (interactive OpenAPI docs at `/docs`)
- **Postgres** — `localhost:5432`

Owner credentials are written to `.env.dev` (`OWNER_EMAIL` / `OWNER_PASSWORD`).

## Repo layout

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app, SQLAlchemy 2 async, Alembic migrations, pytest suite, event store + projections |
| `frontend/` | React 19 + Vite + Tailwind; OpenAPI-generated types, Vitest suite |
| `scripts/` | Operational tooling — migrations, projection replay/rebuild, the assembly-line backfill engine |
| `ops/` | Docker Compose, nginx, n8n deploy workflow |
| `docs/` | Architecture, operator runbooks, contributor onboarding |
| `print-sales-v2/` | Original product specs + implementation plan (archived for reference) |

## Engineering practices

- **Tests first** — 389 backend test modules + a frontend Vitest suite; pre-commit hooks and CI (`ruff`, type checks, OpenAPI-drift guard, build).
- **Migrations are reversible** and verified up/down; data migrations are dry-run-first with reconciliation.
- **Conventional, reviewable PRs** — every feature shipped as an isolated, tested change with a clear history.

## Docs

- Architecture overview → [`docs/architecture.md`](docs/architecture.md)
- Contributor onboarding → [`ONBOARDING.md`](ONBOARDING.md)
- Operations + runbooks → [`OPERATIONS.md`](OPERATIONS.md)
- API surface → [`API.md`](API.md) (+ live OpenAPI at `/docs`)
- Phase-by-phase history → [`CHANGELOG.md`](CHANGELOG.md)

## License

Shared publicly as a portfolio / work sample. © Bengtson Precision 3D — all rights reserved. Not licensed for reuse, redistribution, or production use.
