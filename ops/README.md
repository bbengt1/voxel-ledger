# `ops/`

Operations artifacts: Docker Compose targets, deployment workflows, infrastructure config.

## What lives here

- `docker-compose.yml` and `docker-compose.prod.yml` — lands in [#3](https://github.com/bbengt1/voxel-ledger/issues/3).
- `n8n/web01-deploy.json` — canonical deploy workflow; lands in [#9](https://github.com/bbengt1/voxel-ledger/issues/9).
- `nginx/` — reverse proxy + TLS termination config (Phase 12).
- `systemd/` — service unit files (Phase 12).

## Deployment targets

The legacy v1 app is still live on `web01.bengtson.local`. v2 will deploy to the same host once it reaches Phase 12 cutover. See [`../agents.md`](../agents.md) for the canonical paths (`/srv/3d-print-sales/...`), env file location, and post-deploy checks.

## Related

- [`../print-sales-v2/11_operations_deployment.md`](../print-sales-v2/11_operations_deployment.md) — operations spec.
- [`../docs/`](../docs/) — runbooks and architecture docs.
