# `backend/`

FastAPI application (Python 3.12+) for the Voxel Ledger / Print Sales v2 rewrite.

## Status

Phases 0–4 implemented. Identity & access, the event log + projection engine, catalog (materials/supplies/rates/products/BOM/custom fields/attachments/notes), inventory (locations/transactions/on-hand/alerts), and accounting (chart of accounts/journal entries/periods/approvals/divisions/budgets) are live. Phase 5 (jobs + Moonraker) is filed but not landed. See [`../docs/migrations.md`](../docs/migrations.md) for the full migration changelog and [`../docs/architecture.md`](../docs/architecture.md) for an implementation map.

## Layout

- `app/`
  - `core/` — settings, logging, async database session factory, request middleware.
  - `api/v1/` — thin HTTP routers. No business logic.
  - `services/` — business logic, organized by bounded context. Every accounting mutation goes through the event store inside the caller's DB transaction.
  - `models/` — SQLAlchemy 2 async ORM models.
  - `schemas/` — Pydantic request/response shapes (the contract surface for OpenAPI).
  - `events/` — typed event payloads + the registry. New event types register themselves at module import; `app/events/types/*` are the per-context payload modules.
  - `projections/` — projection handlers. Each handler subscribes to one or more event types via the `@projection(...)` decorator from [#22](https://github.com/bbengt1/voxel-ledger/pull/31) and runs synchronously inside the same DB transaction as the event append.
- `alembic/versions/` — 21 migrations as of Phase 4 end. Mandatory on every schema-changing deploy. Safe-to-rerun.
- `tests/` — pytest. Unit tests use SQLite for speed; integration tests use an ephemeral Postgres fixture via testcontainers (`@pytest.mark.integration`).

## Quick start

The repo-root `make bootstrap` covers everything (creates a venv, generates `.env.dev`, brings up compose, applies migrations, seeds an owner). For backend-only iteration:

```bash
source .venv/bin/activate          # repo-root venv managed by the Makefile
cd backend
pytest -q                          # unit tests, SQLite-backed
pytest -q -m integration           # opt in to PG-via-testcontainers
ruff check . && ruff format --check .
```

See [`../docs/development.md`](../docs/development.md) for the full dev loop.

## Conventions

- All async (no sync DB calls).
- Service-layer functions are the unit of business behavior; routers are dumb adapters.
- Frontend types are generated from the OpenAPI spec — see [`../docs/openapi-codegen.md`](../docs/openapi-codegen.md). Do not hand-maintain type shapes on the client.
- Every business mutation emits an event via `EventStore.append(...)` inside the caller's transaction. The audit projection (`platform.*` wildcard handler) picks them all up automatically.
- ENUM columns are declared `SAEnum(*VALUES, name="...", create_type=False)` in the model. **[`../agents.md`](../agents.md)** has the four PG strict-typing gotchas this codebase has hit — read it before adding any new ENUM.

## Related

- [`../docs/architecture.md`](../docs/architecture.md) — current implementation map.
- [`../docs/event_catalog.md`](../docs/event_catalog.md) — every event type by aggregate.
- [`../docs/migrations.md`](../docs/migrations.md) — reverse-chronological migration changelog.
- [`../print-sales-v2/`](../print-sales-v2/) — original design specs (historical).
- [`../agents.md`](../agents.md) — collaboration rules + PG strict-typing patterns.
