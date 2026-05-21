# Onboarding

Zero-to-first-PR for a new contributor. Read top to bottom the first time; later you'll bounce around.

## 1. Prerequisites

| Tool | Min version | Notes |
| --- | --- | --- |
| Python | 3.12 | Backend + scripts |
| Node | 20.11 | Frontend |
| pnpm | 9 | Workspace manager — not npm, not yarn |
| Docker | 24 | Local stack (Compose v2) |
| make | any | Drives the bootstrap pipeline |

macOS users: Homebrew has all of the above. Linux users: distro packages are fine except pnpm — install via `corepack enable && corepack prepare pnpm@9 --activate`.

## 2. Bootstrap

```bash
git clone git@github.com:bbengt1/voxel-ledger.git
cd voxel-ledger
make bootstrap
```

`make bootstrap` is the source of truth for the local dev loop. It:

1. Verifies your toolchain.
2. Generates `.env.dev` with random secrets if missing.
3. Creates `.venv/` and installs the backend in editable mode plus dev deps.
4. Installs frontend deps (`pnpm install`).
5. Brings up the Docker Compose stack (Postgres + backend with hot reload + frontend with HMR).
6. Waits for healthchecks.
7. Runs Alembic migrations.
8. Seeds the owner user from `.env.dev`.

Re-running on a healthy tree is a fast no-op.

When you're done for the day: `make down` (preserves volumes). To start from scratch: `make nuke` then `make bootstrap`.

## 3. Repo tour

```
backend/
  app/
    api/v1/             # FastAPI routers, one file per bounded context
    core/               # db, settings, middleware, security
    events/types/       # Pydantic payloads + register_event() calls
    models/             # SQLAlchemy ORM, one per table
    projections/        # event -> read-model handlers (audit, balances, ...)
    schemas/            # Pydantic request/response models
    services/           # business logic; routers stay thin
    workers/            # cron-driven background jobs
  alembic/versions/     # migrations, numbered 0001..NNNN
  tests/                # pytest suite + helpers
frontend/
  src/
    api/                # openapi.json + generated types.ts + typed wrapper
    app/                # providers, root layout
    components/         # UI primitives (Button, Dialog, ...) + domain pieces
    pages/              # one folder per route family
    store/              # zustand stores (auth)
ops/
  docker-compose*.yml
  n8n/                  # deploy workflow stub
  nginx/                # web01 production config
```

A few patterns to internalize:

- **Events are the source of truth.** Any accounting-affecting mutation appends a domain event in `event_store.append()` inside the same transaction as the row write. Projections derive everything else (`audit_log`, account balances, inventory on-hand, ...).
- **Settings** are typed via `SettingSchema` subclasses in `backend/app/services/settings/schemas.py`. Adding a new tunable means registering a schema, not a free-form INSERT.
- **Reference numbers** (invoice, bill, sale, ...) go through the race-safe allocator in `app/services/reference.py`. Never `COUNT(*)`.
- **Frontend types are generated.** Edit a Pydantic schema → `make codegen` (or it runs in `pnpm run prebuild`) → CI fails if you hand-edit `frontend/src/api/types.ts`.
- **Tests use SQLite in memory.** `app_session` fixture is the one bound to the running app; the plain `session` fixture is isolated.

## 4. Day-1 dev loop

```bash
# Backend tests
cd backend && ../.venv/bin/python -m pytest

# Frontend tests
cd frontend && pnpm exec vitest run

# Tighter loops:
pnpm exec vitest                   # watch
pnpm exec tsc --noEmit             # typecheck
pnpm exec eslint .                 # lint
ruff check .                       # backend lint
```

If you change anything that touches the OpenAPI surface (a schema, a router signature, a new endpoint), regenerate the frontend types:

```bash
VOXEL_LEDGER_PYTHON=$(pwd)/.venv/bin/python ./scripts/export-openapi.sh
cd frontend && pnpm run codegen
```

CI will fail loudly if you forget.

## 5. Adding a new feature — the short version

1. **Find the right bounded context.** A new bill-related endpoint goes in `backend/app/api/v1/bills.py` and `services/bills.py`. Don't create a new module unless you're starting a fresh aggregate.
2. **Service first, router thin.** Validation, transactions, and event emission live in `services/`. Routers map HTTP errors and commit.
3. **Migration if you need a column.** `cd backend && ../.venv/bin/alembic revision -m "short_name"`. Per [`agents.md`](agents.md) gotcha #1: do NOT pre-create PG enums; let `op.create_table` do it.
4. **Pydantic schema + typed router signature.** Codegen produces the frontend type for free.
5. **Tests.** Unit tests for the service, endpoint tests for the router. Aim for the audit-log assertion ("did the right event land?") when accounting state changes.
6. **Frontend.** New page → `frontend/src/pages/<context>/`. Use the typed `api` client from `@/api/typed`. Vitest test for headline behavior.

## 6. PR conventions

- **Branch name**: `phase-N-X-<slug>` for roadmap work, otherwise `<kind>/<slug>`.
- **Commit messages**: imperative, ≤72 chars summary; body explains the "why" not the "what".
- **PR title**: matches the lead commit. Phase work is `Phase N.X: <summary> (#<issue>)`.
- **PR body**: a Summary + a Test plan section. The PR template prompts for both.
- **CI must pass**: backend pytest + ruff, frontend vitest + tsc + eslint, codegen drift check. There is no manual merge of a red PR.
- **Squash-merge**, delete branch. Linear history.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the long version (pre-commit hooks, signing, etc).

## 7. Where to ask

- Architecture questions → [`docs/architecture.md`](docs/architecture.md) and the per-context spec under `print-sales-v2/`.
- "Where's that pattern?" → grep the codebase; almost every domain has a near-twin you can crib from.
- Stuck on a specific bug → open a draft PR; reviews unblock faster than chat threads.

Welcome aboard.
