# 11. Operations & Deployment Runbook

## 11.1 Environments

| Env | Host | URL | Purpose |
|---|---|---|---|
| Local dev | developer laptop | http://localhost:5173 | Vite dev server + FastAPI |
| Production | `web01.bengtson.local` | https://web01/ | The live business app |

**No staging.** v2 keeps a two-environment topology (local + prod). All testing happens locally before deploying. Migrations and seed data must remain safe to rerun, since prod is the first place new code meets real data.

## 11.2 Build

**Backend container:** multi-stage Dockerfile, base `python:3.13-slim`, runs `uvicorn app.main:app`.

**Frontend container:** multi-stage Dockerfile — Node build stage produces `dist/`, runtime stage is nginx serving `dist/` and reverse-proxying `/api/v1/*` to backend.

**Compose files:**
- `docker-compose.yml` — development (volume mounts, hot reload, exposed ports).
- `docker-compose.prod.yml` — production (built images, persistent volumes, nginx behind external ingress).

## 11.3 Deploy

**Canonical:** n8n workflow `web01-deploy` (defined at `ops/n8n/web01-deploy.json`). Runs:
1. SSH into `web01`, `git pull` in `/srv/3d-print-sales/repo`.
2. `alembic upgrade head` (DB migrations).
3. `scripts/web01-compose.sh up -d --build`.
4. Health-check `curl /health` and `curl /`.
5. Report per-step status.

**Fallback (manual):**
```bash
ssh root@web01.bengtson.local
cd /srv/3d-print-sales/repo
git pull
/srv/3d-print-sales/deploy.sh          # wraps scripts/deploy.sh: pull + migrate + rebuild + restart
# OR for code-only emergency (no schema delta):
SKIP_MIGRATIONS=1 /srv/3d-print-sales/deploy.sh
```

**Hard rule:** migrations MUST run on every schema-changing deploy. Skipping crashes the container at startup. (Real incident 2026-05-09 with PR #271 / #239.)

## 11.4 Filesystem Layout on `web01`

```
/srv/3d-print-sales/
  repo/                          # git checkout
  env/web01.env                  # server env file (secrets)
  data/
    attachments/                 # uploaded files
    pg/                          # postgres data volume
  deploy.sh                      # thin wrapper to repo/scripts/deploy.sh
  backups/                       # nightly dumps
```

## 11.5 Systemd

- Unit: `3d-print-sales.service`
- `systemctl status 3d-print-sales` to inspect.
- `systemctl reload 3d-print-sales` is mapped to a graceful compose rebuild.

## 11.6 Health Checks

```bash
cd /srv/3d-print-sales/repo && scripts/web01-compose.sh ps   # containers up?
curl -fsS http://127.0.0.1/health                            # backend up?
curl -I http://127.0.0.1/                                    # frontend served?
```

Recent logs:
```bash
scripts/web01-compose.sh logs --tail=200 backend
scripts/web01-compose.sh logs --tail=200 frontend
scripts/web01-compose.sh logs --tail=200 db
```

## 11.7 Monitoring & Alerting (recommended for v2)

Today: container health + manual log review.

Recommended:
- Uptime check on `/health` from outside (UptimeRobot or self-hosted).
- Container restart-loop alert.
- DB disk-usage alert at 70% / 85%.
- WS reconnect-storm alert.
- Email-delivery failure alert.
- Background job last-success staleness alert.

Add OpenTelemetry traces + a self-hosted backend (Tempo/Jaeger) in v2.

## 11.8 Logging

- All containers log to stdout/stderr; captured by Docker.
- Recommend structured JSON logs with `request_id` in v2.

## 11.9 Backup & Recovery

**Backup:**
- Nightly `pg_dump` to `/srv/3d-print-sales/backups/` (retain 30 days).
- Rsync `/srv/3d-print-sales/data/attachments` to offsite nightly.

**Recovery drill (target ≤ 2 h):**
1. Restore DB: `pg_restore` from latest dump.
2. Restore attachments: rsync from offsite.
3. Bring up stack: `scripts/web01-compose.sh up -d --build`.
4. Run `alembic upgrade head` (idempotent).
5. Smoke test the 6 user journeys from [08 §8.3](08_ui_ux.md).

## 11.10 Scaling & Failover

- Single host today; no failover.
- Vertical scale: bump VM cores/RAM, restart compose.
- If demand grows: split backend → API + worker for background jobs; put PostgreSQL on its own host or managed service; put nginx behind a real load balancer.

## 11.11 Configuration (env vars)

Loaded by `pydantic-settings` from `web01.env`. Key vars:

| Var | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN (asyncpg) |
| `JWT_SECRET` | Token signing |
| `JWT_ALGORITHM`, `JWT_EXPIRY_MIN` | Token tuning |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Seeded admin (placeholder values block startup) |
| `BACKEND_CORS_ORIGINS` | CORS allow-list |
| `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_BURST` | Rate limiter |
| `TESTING` | Test-mode switch |
| `AUTO_CREATE_SCHEMA` | Dev convenience for `Base.metadata.create_all` |
| `SMTP_*` | Email delivery |
| `MOONRAKER_*` | Printer monitoring tuning |
| `CAMERA_*` | Camera proxy tuning |
| `ATTACHMENTS_DIR` | File upload path (local disk: `/srv/3d-print-sales/data/attachments`) |
| `SHIPPING_PROVIDER` | `easypost` \| `shipstation` |
| `SHIPPING_API_KEY` | Carrier aggregator API key |
| `WEBHOOK_HMAC_KEY` | Secret used to sign outbound webhook payloads (per-target secret is layered on top) |
| `REFRESH_TOKEN_TTL_DAYS` | Refresh token lifetime (default 30) |
| `ACCESS_TOKEN_TTL_MINUTES` | Access token lifetime (default 15) |

## 11.12 Migrations

- `alembic upgrade head` on every deploy.
- New migrations live in `backend/alembic/versions/`.
- **Postgres-compatibility constraints** (from project memory):
  - Boolean defaults must use `text("false")`/`text("true")` so PG accepts them.
  - Never double-create an index (use `if_not_exists` semantics or guard).
- Downgrades: present but not part of normal flow.

## 11.13 Release Process

1. Branch from `main`; open PR with passing CI; describe behavior + validation.
2. Merge to `main`.
3. Trigger n8n `web01-deploy` workflow.
4. Verify post-deploy checks pass.
5. Update relevant docs in the same PR (project rule).

## 11.14 Incident Response (skeleton)

| Severity | Definition | Response |
|---|---|---|
| Sev 1 | App down or data corruption | Page owner; roll back to prior image; restore from backup if needed |
| Sev 2 | Major feature broken (POS, sale entry, reports wrong) | Hotfix branch; deploy fix within business day |
| Sev 3 | Minor regression or visual bug | Track issue; bundle into next release |

Roll-back: `git checkout <prior_sha> && /srv/3d-print-sales/deploy.sh`. If migrations were applied, run the explicit downgrade or roll forward with a corrective migration — never edit the DB ad-hoc.

## 11.15 Maintenance Windows

Off-hours (small business). Announce in advance for anything > 5 min.

## 11.16 Capacity Planning

Today's load is trivially served by 4 cores / 8 GB. Re-evaluate annually or when:
- DB size > 30 GB.
- Backend p95 latency > 800 ms on a list endpoint.
- Container CPU sustained > 60%.

## 11.17 v2 Cutover Checklist

- [ ] v2 stack deployed alongside v1 on staging host.
- [ ] Data migration scripts validated against a copy of production.
- [ ] Reference numbers (sale/invoice/quote) preserved.
- [ ] Inventory + accounting balances tie to v1 outputs.
- [ ] User accounts re-seeded; passwords either preserved or reset with email.
- [ ] Cutover window agreed; v1 set read-only during final sync.
- [ ] DNS / ingress switched to v2.
- [ ] v1 archived (not deleted) for at least one tax year.
