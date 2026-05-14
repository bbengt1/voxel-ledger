# `ops/`

Operations artifacts: Docker Compose targets, deployment workflows, infrastructure config.

## What lives here

- `../docker-compose.yml` (repo root) — dev stack.
- `../docker-compose.prod.yml` (repo root) — prod stack.
- `../scripts/compose.sh` — wrapper that picks the right compose file + env file.
- `nginx/default.conf` — reverse proxy config for the prod stack. Reverse-proxies `/api/` and `/health` to the backend; serves the SPA from the built frontend assets. TLS termination is a commented-out placeholder until Phase 12.
- `nginx/frontend-fallback.conf` — minimal nginx config baked into the frontend image so it can serve the SPA standalone for debugging.
- `n8n/web01-deploy.json` — canonical deploy workflow; lands in [#9](https://github.com/bbengt1/voxel-ledger/issues/9).
- `systemd/` — service unit files (Phase 12).

## Compose stacks

### Dev (`docker-compose.yml`)

| Service | Image / build | Notes |
|---|---|---|
| `db` | `postgres:16-alpine` | Named volume `db_data`. Port 5432 exposed for local psql. |
| `backend` | `backend/Dockerfile` target `dev` | Source bind-mounted at `/app`. Runs `uvicorn --reload`. |
| `frontend` | `node:20-alpine` | Repo bind-mounted at `/repo`. Runs `pnpm dev` via corepack. Vite HMR on 5173. |

Bring up:

```bash
cp .env.dev.example .env.dev
scripts/compose.sh up -d --build
```

### Prod (`docker-compose.prod.yml`)

| Service | Image / build | Notes |
|---|---|---|
| `db` | `postgres:16-alpine` | Bind-mounted at `${PG_DATA_DIR}` (default `/srv/3d-print-sales/data/pg`). |
| `backend` | `backend/Dockerfile` target `runtime` | Entrypoint runs `alembic upgrade head` then `uvicorn`. Fails fast on missing migrations. `SKIP_MIGRATIONS=1` for code-only emergencies. |
| `frontend` | `frontend/Dockerfile` | Multi-stage: Node builds `dist/`, nginx serves it. |
| `nginx` | `nginx:1.27-alpine` | Reverse-proxies `/api/` and `/health` to backend; serves SPA from the frontend container's web root. TLS placeholder. |

Bring up (on `web01`, with the env file in place):

```bash
scripts/compose.sh --prod up -d --build
```

## Local ↔ prod path mapping

| Concern | Local dev | Prod (`web01`) |
|---|---|---|
| Repo checkout (host) | wherever you cloned it | `/srv/3d-print-sales/repo` |
| Env file (host) | `<repo>/.env.dev` | `/srv/3d-print-sales/env/web01.env` |
| Postgres data | Docker named volume `db_data` | bind-mount `/srv/3d-print-sales/data/pg` |
| Attachments (Phase 2+) | (not yet wired) | `/srv/3d-print-sales/data/attachments` |
| Backend port (host) | `${BACKEND_HOST_PORT:-8000}` | not exposed; reached via nginx |
| Frontend port (host) | `${FRONTEND_HOST_PORT:-5173}` | not exposed; reached via nginx |
| Public ingress | `http://localhost:5173` (Vite), `http://localhost:8000` (API) | `http(s)://web01/` via the `nginx` service |

Inside containers the service hostnames are the compose service names: `db`, `backend`, `frontend`, `nginx`. The backend reaches Postgres at `db:5432`.

## Env file convention

- `.env.dev.example` is the source of truth for which variables exist in dev. Copy to `.env.dev` (gitignored) and fill in real values.
- `.env.prod.example` is the source of truth for prod. On `web01` the populated file lives at `/srv/3d-print-sales/env/web01.env` and is never committed.
- `scripts/compose.sh` passes the selected env file via `--env-file` (for compose-level interpolation) and the compose YAML also references it via per-service `env_file:` entries (for runtime container env).
- Override the prod env-file path with `ENV_FILE=/some/other/path scripts/compose.sh --prod ...` — handy for testing the prod stack locally.

## How `scripts/compose.sh` picks a stack

The wrapper checks two things, in order: an explicit `--prod` or `--dev` flag (consumed before forwarding), and the `ENV` environment variable (`ENV=prod` selects prod, anything else selects dev). Once a stack is chosen it points `docker compose` at the matching compose file and env file, then forwards every remaining argument verbatim. Defaults to dev with no flag and no `ENV` set.

## Deployment targets

The legacy v1 app is still live on `web01.bengtson.local`. v2 will deploy to the same host once it reaches Phase 12 cutover. See [`../agents.md`](../agents.md) for the canonical paths (`/srv/3d-print-sales/...`), env file location, and post-deploy checks.

## Related

- [`../print-sales-v2/11_operations_deployment.md`](../print-sales-v2/11_operations_deployment.md) — operations spec.
- [`../docs/`](../docs/) — runbooks and architecture docs.
