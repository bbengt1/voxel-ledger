# Operations

Production-ops checklist. The exhaustive runbook is [`docs/web01_runbook.md`](docs/web01_runbook.md) — this file is the short, scannable overview.

## 1. Topology

- Single VM: `web01.internal`.
- Docker Compose stack: Postgres 16 + FastAPI backend + Vite-built frontend behind nginx.
- Systemd unit `3d-print-sales.service` brings the stack up on boot.
- Deploys orchestrated by an n8n workflow ([`docs/deployment_n8n_workflow.md`](docs/deployment_n8n_workflow.md)); manual fallback documented in the web01 runbook.
- Off-hours maintenance windows are acceptable — uptime target 99.5%.

## 2. Filesystem layout

| Path | Purpose |
| --- | --- |
| `/srv/3d-print-sales/repo/` | Git checkout |
| `/srv/3d-print-sales/env/web01.env` | Production secrets (never committed) |
| `/srv/3d-print-sales/data/pg/` | Postgres data (bind-mounted) |
| `/srv/3d-print-sales/data/attachments/` | Uploaded files |
| `/srv/3d-print-sales/backups/` | Nightly `pg_dump` tarballs |

## 3. Routine deploy

```bash
# n8n preferred path
trigger "Voxel Ledger deploy" in n8n

# Manual fallback
ssh deploy@web01.internal
cd /srv/3d-print-sales/repo
/srv/3d-print-sales/deploy.sh
```

The deploy script: pulls `main`, rebuilds the backend image, runs `alembic upgrade head` (mandatory — startup crashes on missing migrations by design), restarts the stack, then verifies `/health` is 200.

## 4. Backups + restore

Daily nightly `pg_dump` to `/srv/3d-print-sales/backups/`. Attachments rsynced to the same path. **Phase 12.2 ([#204](https://github.com/bbengt1/voxel-ledger/issues/204))** lands continuous WAL archiving + an automated restore drill — until that ships, restore is `pg_restore` from the latest nightly dump.

To do a manual restore drill against a temp DB:

```bash
ssh deploy@web01.internal
sudo -u postgres pg_restore --clean --if-exists --dbname=test_restore /srv/3d-print-sales/backups/<timestamp>.dump
```

Smoke checks: row counts on `event` (chain length), `journal_entry`, `invoice`, and `bill`. If those parity-match the live counts, the dump is good.

## 5. Common incidents

| Symptom | First check | Fix |
| --- | --- | --- |
| Stack down after deploy | `scripts/web01-compose.sh logs backend` | Usually a failed migration — `alembic current` + manual rollback |
| 503 from nginx | `scripts/web01-compose.sh ps` | Container crashed; check backend logs |
| Frontend stale after deploy | Browser cache | `Cmd+Shift+R`; if persistent, `docker volume prune` then re-deploy |
| Background job not running | `select * from event order by position desc limit 5` | Worker registered? Check `app/workers/registry.py` and cron unit |
| Webhook deliveries stuck | `select count(*) from webhook_delivery where last_status='pending'` | Confirm `webhook_dispatcher` cron firing (every minute) |
| DLQ growing | Check `/api/v1/control-center` → `webhook_dlq` | Investigate target endpoint; manual replay via `POST /api/v1/webhooks/deliveries/{id}/replay` |

## 6. Logs

Structured JSON to stdout, captured by Docker. Tail:

```bash
scripts/web01-compose.sh logs -f backend
journalctl -u 3d-print-sales -f          # systemd-level
```

Every request carries an `x-request-id`; reuse it when filing incidents.

## 7. Observability

- `/health` — liveness probe (returns 200 + last-known migration revision).
- `/api/v1/control-center` — admin "things to look at" aggregate (pending approvals, overdue, webhook DLQ, low stock).
- Worker last-run state lives in the per-worker logs for now; a `worker_run_state` table is Phase 12 follow-up.

## 8. Maintenance windows

| Task | Cadence | Where |
| --- | --- | --- |
| Postgres `VACUUM ANALYZE` | Weekly via cron | `ops/cron/` |
| Backup verification | Monthly | Restore drill from §4 |
| Dependency upgrade pass | Quarterly | `pnpm up -L` + `uv pip compile` |
| Security patch | As-needed | Watch `dependabot` PRs |

## 9. Emergency contacts + escalation

- Repo: https://github.com/bbengt1/voxel-ledger
- Owner: `owner@bengtsonprecision3d.com`
- Hosting: single VM, no cloud provider escalation path.

If the site is down and the deploy script + nginx restart didn't fix it, the highest-leverage move is `scripts/web01-compose.sh down && scripts/web01-compose.sh up -d`. Postgres data is on a bind mount, so the worst case from a bad container is a 30s outage.
