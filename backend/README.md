# `backend/`

FastAPI application (Python 3.12+) for the Voxel Ledger / Print Sales v2 rewrite.

## What lives here

- `app/` — application code, organized by **bounded context** (Identity & Access, Catalog, Inventory, Production, Sales, AR, AP, Banking, Accounting, Reporting, Notifications, Platform). Not by technical layer.
  - `core/` — settings, logging, database session factory, request middleware.
  - `api/v1/` — thin HTTP routers. No business logic.
  - `services/` — business logic. All accounting mutations go through the event store inside the caller's DB transaction.
  - `models/` — SQLAlchemy 2 async ORM models.
  - `schemas/` — Pydantic request/response shapes (the contract surface for OpenAPI).
- `alembic/` — migrations. Mandatory on every schema-changing deploy. Safe-to-rerun.
- `tests/` — pytest. Unit tests use SQLite for speed; integration tests use an ephemeral Postgres fixture.

## Quick start

The skeleton lands in [#2](https://github.com/bbengt1/voxel-ledger/issues/2). Until then, this directory is intentionally empty.

## Conventions

- All async (no sync DB calls).
- Service-layer functions are the unit of business behavior; routers are dumb adapters.
- Frontend types are generated from the OpenAPI spec — see [`../docs/openapi-codegen.md`](../docs/) (lands in [#5](https://github.com/bbengt1/voxel-ledger/issues/5)). Do not hand-maintain type shapes on the client.

## Related

- [`../print-sales-v2/04_architecture.md`](../print-sales-v2/04_architecture.md) — architectural decisions.
- [`../print-sales-v2/07_module_specifications.md`](../print-sales-v2/07_module_specifications.md) — per-module specs.
- [`../print-sales-v2/IMPLEMENTATION_PLAN.md`](../print-sales-v2/IMPLEMENTATION_PLAN.md) — phased roadmap.
- [`../agents.md`](../agents.md) — collaboration rules.
