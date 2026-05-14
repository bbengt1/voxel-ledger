# Local development guide

This walks a cold contributor from `git clone` to a running stack with a
working login. The bootstrap is one command. The rest of this file explains
what that command does, what the dev loop looks like, and what to do when
things go sideways.

> For collaboration norms (PR shape, codegen-drift contract, commit style),
> read [`agents.md`](../agents.md). For the phased roadmap, see
> [`print-sales-v2/IMPLEMENTATION_PLAN.md`](../print-sales-v2/IMPLEMENTATION_PLAN.md).

## Prerequisites

You need the following on `PATH`. `make bootstrap` checks all of these and
refuses to proceed on a mismatch (`scripts/check_tools.sh` enforces the
minimums):

| Tool             | Minimum  | Notes                                              |
|------------------|----------|----------------------------------------------------|
| Python           | 3.12     | A venv is recommended but not required by `make`.  |
| Node             | 20.11    | Same major as CI.                                  |
| pnpm             | 9        | `corepack enable` will pin the exact version.      |
| Docker           | recent   | Daemon must be running.                            |
| `docker compose` | v2       | The plugin, not the legacy `docker-compose` binary.|
| openssl          | any      | Used to generate local dev secrets.                |

Linux contributors: make sure your user is in the `docker` group so
`docker info` succeeds without sudo.

## One-command bootstrap

```bash
git clone git@github.com:bbengt1/voxel-ledger.git
cd voxel-ledger
make bootstrap
```

Bootstrap is idempotent — re-running on a working tree is a fast no-op. The
pipeline (`make help` lists each step as its own target) does:

1. **`check-tools`** — version-checks Python/Node/pnpm/Docker/openssl.
2. **`env-dev`** — if `.env.dev` is missing, copies `.env.dev.example` and
   substitutes locally-safe random values for `JWT_SECRET_KEY`, the Postgres
   password, and an `OWNER_PASSWORD`. The owner email defaults to
   `owner@voxel-ledger.local`. The file is tagged `# LOCAL DEV ONLY` and
   gitignored.
3. **`install`** — `pip install -e backend/[dev]` and `pnpm install`.
4. **`up`** — `scripts/compose.sh up -d --build` brings the dev stack up
   (Postgres, FastAPI backend with hot reload, Vite frontend with HMR).
5. **`wait-healthy`** — polls until db and backend healthchecks pass.
6. **`migrate`** — `alembic upgrade head` inside the backend container.
7. **`seed`** — `python -m scripts.seed_owner` creates the owner user from
   `OWNER_EMAIL` / `OWNER_PASSWORD`. Idempotent — exits clean if the user
   table is non-empty.
8. **`summary`** — prints URLs, the owner password lives in `.env.dev`, and
   the most-useful follow-up commands.

Expected output of `make summary` (the final step):

```
Voxel Ledger dev stack is up.
  Frontend:  http://localhost:5173
  Backend:   http://localhost:8000  (docs: /docs)
  Postgres:  localhost:5432

Owner credentials are in .env.dev (OWNER_EMAIL / OWNER_PASSWORD).
Useful: make logs | make down | make nuke | make test
```

Open <http://localhost:5173>, log in with the credentials from `.env.dev`,
and you're in.

## Dev loop

The compose stack is set up so you almost never have to restart anything.

- **Backend**: source-mounted at `/app`. `uvicorn --reload` watches the tree
  and reloads on save. Logs: `make logs` or
  `scripts/compose.sh logs -f backend`.
- **Frontend**: source-mounted at `/repo/frontend`. Vite HMR pushes updates
  to the browser without a refresh. Logs:
  `scripts/compose.sh logs -f frontend`.
- **Database**: data lives in the `db_data` named volume. Drop into a shell
  with `make psql`.
- **Tests**: `make test` runs backend `pytest -q` inside the container and
  the frontend `vitest` suite on the host. `make test-backend` and
  `make test-frontend` are the split targets.

### Backend schema changes → regenerate types

The OpenAPI spec is the contract. After touching any Pydantic schema,
FastAPI route, or response model, regenerate the spec and TS types:

```bash
pnpm run codegen:export    # backend → openapi.json
pnpm run codegen           # openapi.json → src/api/types.ts
```

CI fails on drift via `pnpm run codegen:check`. Commit the regenerated
`frontend/src/api/openapi.json` and `frontend/src/api/types.ts` with the
backend change. See [`openapi-codegen.md`](openapi-codegen.md) for the
contract.

### Dev fixtures

The owner seed is automatic. Anything else (materials, products, printers,
customers) is opt-in:

```bash
make seed-fixtures
```

Phase 0 has no fixture-eligible tables beyond `user`, so this is a no-op
today. The scaffold lives at `backend/app/seed/dev_fixtures.py` and is
where Phase 1+ will land real fixtures.

## Common failure modes

**Port already in use (`5432`, `8000`, `5173`).** Set
`POSTGRES_HOST_PORT` / `BACKEND_HOST_PORT` / `FRONTEND_HOST_PORT` in
`.env.dev` to free ports and run `make down && make up`. The compose file
honours those overrides.

**Stale containers / volumes.** Two services pinning incompatible schemas
across a branch switch is the classic symptom. The blast-radius reset:

```bash
make nuke         # destroys containers AND volumes (prompts)
make bootstrap    # clean rebuild
```

**Schema drift between branches.** If you've just `git switch`ed onto a
branch with new migrations, `make migrate` is enough — the data volume
survives. If migrations conflict, fall back to `make nuke && make bootstrap`.

**Lockfile churn.** `pnpm-lock.yaml` updates from someone else's branch
mean the in-container `pnpm install` step will re-resolve. If the frontend
container is in a weird state, `make down && make up` rebuilds with the
fresh lockfile. The lockfile-related volume on rebuild is normal and quick.

**`docker compose` not found.** You may have the legacy `docker-compose`
v1 binary. Install the v2 plugin (it ships with Docker Desktop; on Linux
install `docker-compose-plugin`).

**`make bootstrap` fails on `check-tools`.** Read the error — it names the
tool and minimum version. Upgrade, then re-run; bootstrap picks up where it
left off.

**Backend container restart-loops with a placeholder rejection.** The
`Settings` validator rejects sentinel values (`changeme`, etc.) on purpose.
Delete `.env.dev` and re-run `make env-dev` to regenerate fresh secrets.

## Clean reset

When all else fails:

```bash
make nuke && make bootstrap
```

This wipes the containers and the Postgres volume but leaves `.env.dev` in
place so your owner password stays stable across resets. Delete `.env.dev`
first if you also want fresh secrets.

## Reference

- [`agents.md`](../agents.md) — collaboration rules.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — CI, pre-commit, PR conventions.
- [`openapi-codegen.md`](openapi-codegen.md) — codegen-drift contract.
- [`web01_runbook.md`](web01_runbook.md) — production host runbook.
