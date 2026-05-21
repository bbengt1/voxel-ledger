# Voxel Ledger

Single-tenant accounting + operations platform for a 3D-print business. FastAPI + Postgres on the backend, React + Vite on the frontend, event-sourced ledger underneath. Deployed to a single VM via Docker Compose.

## Quick start

```bash
git clone git@github.com:bbengt1/voxel-ledger.git
cd voxel-ledger
make bootstrap
```

That checks your toolchain, generates a local `.env.dev`, builds the dev stack, applies migrations, and seeds an owner. Then:

- Frontend — http://localhost:5173
- Backend — http://localhost:8000 (OpenAPI at `/docs`)
- Postgres — `localhost:5432`

Owner credentials live in `.env.dev` (`OWNER_EMAIL` / `OWNER_PASSWORD`).

## What's here

| Path | Purpose |
| --- | --- |
| `backend/` | FastAPI app, SQLAlchemy 2 async, Alembic migrations, Pytest suite |
| `frontend/` | React 19 + Vite + Tailwind 4 + Radix; OpenAPI-generated types |
| `ops/` | Docker Compose, nginx, n8n deploy workflow, systemd units |
| `docs/` | Operator + contributor docs (see [`ONBOARDING.md`](ONBOARDING.md) and [`OPERATIONS.md`](OPERATIONS.md)) |
| `print-sales-v2/` | Original specs and implementation plan (archived for reference) |

## Status

Phases 0 – 11 shipped. Phase 12 (hardening + v1 cutover) is in progress. See [`CHANGELOG.md`](CHANGELOG.md) for the per-phase summary.

## Architectural non-negotiables

- **Event-sourced accounting.** Domain events are the source of truth; journal entries, balances, and reports are projections. Append-only event log with hash chain.
- **Race-safe reference numbering** via DB-sequence allocator (`{PREFIX}-{YYYY}-{NNNN}`). Never `COUNT(*)`.
- **Frontend types generated from OpenAPI** at prebuild; CI fails on drift.
- **RBAC**: fixed roles (`owner`/`bookkeeper`/`production`/`sales`/`viewer`), deny-by-default.
- **Postgres-native everything** — no Redis/RabbitMQ.
- **Lazy-loaded printer monitoring.** Moonraker WS must not be a startup dependency.
- **Single-tenant, USD-only, no MFA/SSO, no staging environment.**

See [`print-sales-v2/12_glossary_assumptions_decisions.md`](print-sales-v2/12_glossary_assumptions_decisions.md) for the full decision record.

## Docs

- **Contributors** → [`ONBOARDING.md`](ONBOARDING.md)
- **Operators** → [`OPERATIONS.md`](OPERATIONS.md)
- **API consumers** → [`API.md`](API.md) (with live OpenAPI at `/docs` on the running backend)
- **Architecture overview** → [`docs/architecture.md`](docs/architecture.md)
- **Collaboration rules** → [`agents.md`](agents.md)
- **CI / PR conventions** → [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Reporting issues

Use GitHub Issues. Tag with the relevant `phase-*` label if it slots into a roadmap item; otherwise leave untagged for triage.

## License

Private repo, single-tenant deployment. No public license.
