# Voxel Ledger

Full-stack 3D-print business platform — the **v2 rewrite** of the app currently deployed at `web01.bengtson.local`. The legacy app remains in production while v2 is being built; cutover happens at the end of Phase 12.

> **Status:** Phase 0 (Bootstrap). The repo currently holds specs, an implementation plan, and the monorepo scaffolding. Application code lands as Phase 0 issues close.

## Source of truth

- [`print-sales-v2/IMPLEMENTATION_PLAN.md`](print-sales-v2/IMPLEMENTATION_PLAN.md) — phased build plan (Phase 0 bootstrap → Phase 12 hardening/cutover).
- [`print-sales-v2/`](print-sales-v2/) — narrative specs (`01_system_overview.md` through `12_glossary_assumptions_decisions.md`) plus the API reference exported from v1.
- [`agents.md`](agents.md) — collaboration rules, working style, UX laws, deployment references, performance budgets.

## Repository layout

```
voxel-ledger/
├── backend/          # FastAPI + SQLAlchemy 2 async + Postgres 16 (lands in #2)
├── frontend/         # React 19 + Vite + Tailwind 4 + Radix (lands in #4)
├── ops/              # Docker Compose, n8n workflow, nginx, systemd (lands in #3, #9)
├── docs/             # Runbooks, reference, diagrams
├── print-sales-v2/   # Authoritative specs and implementation plan
├── agents.md         # Collaboration guide
├── pyproject.toml    # Root Python tool config (ruff, mypy, pytest)
├── package.json      # Root workspace manifest
└── pnpm-workspace.yaml
```

## Architectural non-negotiables

These are baked into the rewrite and require an explicit decision-record update to change:

- **Event-sourced accounting.** Domain events are the source of truth; journal entries, balances, and reports are projections. Append-only event log with hash chain.
- **Race-safe reference numbering** via DB-sequence allocator (`{PREFIX}-{YYYY}-{NNNN}`). Never `COUNT(*)`.
- **Frontend types generated from OpenAPI** at prebuild; CI fails on drift. No hand-typed resource shapes.
- **RBAC**: fixed roles (`owner`/`bookkeeper`/`production`/`sales`/`viewer`), deny-by-default.
- **Postgres-native job queue** (pg-boss / pgmq + Arq). No Redis/RabbitMQ.
- **Lazy-loaded printer monitoring.** Moonraker WS must not be a startup dependency.
- **Single-tenant, USD-only, no MFA/SSO, no staging environment.**

See [`print-sales-v2/12_glossary_assumptions_decisions.md`](print-sales-v2/12_glossary_assumptions_decisions.md) for the full decision record.

## Quick start

```bash
git clone git@github.com:bbengt1/voxel-ledger.git
cd voxel-ledger
make bootstrap
```

`make bootstrap` checks your toolchain, generates a local `.env.dev` with
random secrets, installs dependencies, brings up the Docker Compose stack
(Postgres + FastAPI with hot reload + Vite with HMR), runs migrations, and
seeds an owner user. It is idempotent — re-running on a working tree is a
fast no-op. Owner credentials are written to `.env.dev`.

For the full dev loop (codegen after backend schema changes, common failure
modes, clean reset, etc.) see [`docs/development.md`](docs/development.md).
For CI / pre-commit / PR conventions, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Development

Tooling stack:

- **Python 3.12+**, managed via virtualenv or `uv`.
- **Node 20.11+**, **pnpm 9** as the workspace manager (chosen over npm/yarn for strict module resolution — see [`pnpm-workspace.yaml`](pnpm-workspace.yaml)).
- **PostgreSQL 16** for development and production.
- **Docker Compose** for local dev.

## Working style

Work is driven through GitHub issues, milestoned by phase. Phase 0 issues live under the [Phase 0 — Bootstrap milestone](https://github.com/bbengt1/voxel-ledger/milestone/1). See [`agents.md`](agents.md) for the full contributor guide.
