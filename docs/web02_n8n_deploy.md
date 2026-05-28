# Deployment via n8n (`web02-deploy`)

Operator runbook for the canonical deploy path: the `web02-deploy` n8n
workflow on `n8n.bengtson.local`.

- **Workflow JSON:** [`ops/n8n/web02-deploy.json`](../ops/n8n/web02-deploy.json)
- **Manual SSH fallback:** [`docs/web02_runbook.md`](web02_runbook.md)
- **First-time host setup:** [`docs/web02_bootstrap.md`](web02_bootstrap.md)
- **Spec reference:** [`print-sales-v2/11_operations_deployment.md`](../print-sales-v2/11_operations_deployment.md) §11.3

## When to use this

Every routine deploy to `web02`. The workflow encapsulates pull → migrate →
rebuild → verify with per-node output, so failure shows up in n8n's run log
instead of a black-box ssh session.

Use the [manual SSH fallback](web02_runbook.md) when:

- n8n is down or unreachable.
- You need to debug a half-broken deploy interactively.
- You're doing something the workflow doesn't cover (e.g. `alembic downgrade`,
  emergency restart, rollback).

## Prerequisites

1. n8n instance reachable at `n8n.bengtson.local` with
   [`web02-deploy.json`](../ops/n8n/web02-deploy.json) imported.
2. An n8n SSH credential named **`web02 ssh (root)`** that authenticates to
   `root@web02.bengtson.local` using the key authorized on the host
   (`~/.ssh/id_ed25519_web02` on the operator's workstation; the matching
   private key needs to be uploaded into the n8n credential).
3. The target commit is already on `origin/main`. The workflow only deploys
   what's on `main`; it does not check out arbitrary branches.

> **GitHub webhook trigger:** intentionally not enabled yet. Inbound webhook
> ingress from github.com to `n8n.bengtson.local` requires a Cloudflare Tunnel
> entry that hasn't been wired up. Until then, deploys are manual-button only.
> When the tunnel is ready, add a `webhook` trigger node feeding the same
> `1. Pull latest main` step; the rest of the workflow stays unchanged.

## Trigger

In the n8n UI:

1. Open the `web02-deploy` workflow.
2. Click **Execute Workflow** (top right).

## Expected runtime

- Healthy deploy: **~2 to 4 minutes**.
- Rebuild dominates the runtime (frontend `pnpm install` + `vite build`).
- Migrations are usually sub-second; allow up to ~30s for larger ones.

## Success signals

All five nodes go green and:

- Node **1. Pull latest main** prints a short SHA matching `origin/main`.
- Node **2. Run migrations** ends with `INFO  [alembic.runtime.migration] ...`
  output and a zero exit. No-op migrations are still success.
- Node **3. Rebuild + rotate containers** prints `docker compose ps` showing
  `db`, `backend`, `frontend`, `nginx` all `Up (healthy)` or `Up`.
- Node **4. Verify /health** returns HTTP 200.
- Node **5. Verify /** returns HTTP 200 or 301.

## Common failure modes

### Step 1 — `git pull` failed
- **Likely cause:** non-fast-forward on `main`, or someone left the checkout
  on a different branch.
- **Fix:** SSH in (see [`web02_runbook.md`](web02_runbook.md)),
  `cd /srv/voxel-ledger/repo`, sort out the checkout state, re-run the
  workflow.

### Step 2 — migration failed
- **Likely cause:** a bad migration (syntax, dependency, irreversible data
  step). Backend has NOT been rebuilt yet at this point, so the running
  containers are still on the previous code. Site is still up.
- **Fix:**
  1. Read the alembic traceback from the node output.
  2. Push a fix to `main` (revert or roll-forward migration).
  3. Re-run the workflow. Do **not** patch in place on the server.
- **Do not** set `SKIP_MIGRATIONS=1` to "get past it." That just defers the
  crash to startup time once you finally rebuild.

### Step 3 — container failed to come up
- **Likely cause:** image build error, missing env var, port conflict, or a
  schema/code mismatch the migration didn't catch.
- **Fix:**
  1. SSH in.
  2. `scripts/web02-compose.sh logs --tail=200 backend` (and `frontend`).
  3. If the previous image is still running on a different name, follow the
     [rollback procedure](web02_runbook.md#rollback-to-a-prior-image).
  4. Otherwise: push a fix to `main` and re-run.

### Step 4 — `/health` check timed out
- **Likely cause:** backend container came up but is still applying a slow
  migration during its own startup, or it's stuck on a startup dependency.
- **Fix:**
  1. Wait 30s and re-run just this node (n8n: right-click → Execute Node).
  2. If still failing, check `scripts/web02-compose.sh logs -f backend` for an
     error or a long-running migration.
  3. If the backend is genuinely down, follow rollback.

### Step 5 — `/` check failed (frontend)
- **Likely cause:** nginx is up but the frontend container hasn't passed its
  own healthcheck, so nginx is returning 502.
- **Fix:** `scripts/web02-compose.sh logs --tail=200 frontend`. Usually a
  build artifact mismatch — rebuild and retry.

## Rollback

The workflow does not roll back automatically. If a deploy fails after the
rebuild step and the previous good state is gone, follow
[`web02_runbook.md` → Rollback to a prior image](web02_runbook.md#rollback-to-a-prior-image).

## Post-deploy sanity (always run after a green workflow)

```bash
ssh web02
cd /srv/voxel-ledger/repo
scripts/web02-compose.sh ps
curl -fsS http://127.0.0.1/health
curl -I http://127.0.0.1/
```

Then do a real smoke check from a browser — login, load the POS, render one
of the report views. Container health is necessary but not sufficient.
