# `web02` manual SSH runbook

The fallback path when [the n8n deploy workflow](web02_n8n_deploy.md) is
unavailable or you need to do something it doesn't cover (rollback, emergency
restart, log dive, `alembic downgrade`).

For one-time host setup, see [web02_bootstrap.md](web02_bootstrap.md).

- **Canonical paths:** [`agents.md` § Deployment Targets](../agents.md)
- **Spec reference:** [`print-sales-v2/11_operations_deployment.md`](../print-sales-v2/11_operations_deployment.md)

## Access

```bash
ssh web02            # ~/.ssh/config alias → deploy@web02.internal
```

## Filesystem layout

| Path | What it is |
|---|---|
| `/srv/voxel-ledger/` | App root |
| `/srv/voxel-ledger/repo/` | Git checkout (`origin` = this GitHub repo) |
| `/srv/voxel-ledger/env/web02.env` | Server env file (secrets — never committed) |
| `/srv/voxel-ledger/data/pg/` | Postgres data (bind-mounted into the `db` container) |
| `/srv/voxel-ledger/data/attachments/` | Uploaded files |
| `/srv/voxel-ledger/backups/` | Nightly `pg_dump` output |
| `/srv/voxel-ledger/deploy.sh` | Thin wrapper that calls `repo/scripts/deploy.sh` with `COMPOSE=scripts/web02-compose.sh` |
| `voxel-ledger.service` (systemd unit) | Lifts the compose stack on boot |

## Compose wrapper

All compose commands on `web02` go through `scripts/web02-compose.sh`, which
sets `ENV_FILE=/srv/voxel-ledger/env/web02.env` and delegates to
`scripts/compose.sh --prod`.

```bash
cd /srv/voxel-ledger/repo
scripts/web02-compose.sh ps
scripts/web02-compose.sh up -d --build
scripts/web02-compose.sh down            # stops containers; preserves volumes
scripts/web02-compose.sh restart backend
```

> **Do not** run `scripts/web02-compose.sh down -v`. The `-v` flag deletes
> named volumes; the Postgres data is a bind-mount so it survives, but
> anything else compose owns gets nuked. Treat `down -v` as a "are you sure
> you wrote a backup first" command.

## Routine deploy (when n8n is down)

Prefer the n8n workflow. If n8n is unavailable:

```bash
ssh web02
/srv/voxel-ledger/deploy.sh
```

`/srv/voxel-ledger/deploy.sh` is the host-side wrapper that invokes
[`scripts/deploy.sh`](../scripts/deploy.sh) inside the repo with
`COMPOSE=scripts/web02-compose.sh`. It runs:

1. `git fetch && git checkout main && git pull --ff-only`
2. `scripts/web02-compose.sh run --rm backend alembic upgrade head`
3. `scripts/web02-compose.sh up -d --build`
4. `scripts/web02-compose.sh restart nginx` — clears stale upstream IPs so
   nginx doesn't serve 502s against the freshly-recreated backend/frontend
   (non-fatal; logged and skipped if nginx isn't in the stack).
5. Polls `http://127.0.0.1/health` for up to 60s.
6. Prints `scripts/web02-compose.sh ps`.

A failed step exits non-zero with a `FAILED at step N` line — read it before
retrying.

### Code-only emergency redeploy (no schema delta)

```bash
SKIP_MIGRATIONS=1 /srv/voxel-ledger/deploy.sh
```

**Hard rule:** migrations must run on every schema-changing deploy. The
backend startup path queries newly-added tables and columns; skipping
migrations crashes the container at boot. `SKIP_MIGRATIONS=1` exists only for
code-only fixes when you *know* the migration list hasn't moved.

## Tail logs

```bash
cd /srv/voxel-ledger/repo
scripts/web02-compose.sh logs -f --tail=200 backend
scripts/web02-compose.sh logs -f --tail=200 frontend
scripts/web02-compose.sh logs -f --tail=200 db
scripts/web02-compose.sh logs -f --tail=200 nginx
```

Drop the `-f` to print and exit.

## Emergency restart

Two flavors, in increasing order of disruption:

```bash
# Restart just the backend container (drops in-flight requests, picks up
# config changes from the env file, ~5–10s).
cd /srv/voxel-ledger/repo
scripts/web02-compose.sh restart backend

# Full stack via systemd (rebuilds nothing; restarts every container).
systemctl restart voxel-ledger.service
```

Neither rebuilds the image. If the running image is the problem, follow
rollback.

## Failed-migration recovery

If `scripts/deploy.sh` or the n8n workflow failed at the migration step:

1. The previous containers are **still running on the previous code** —
   migrations run via `compose run --rm`, before the rebuild. Site is up.
2. Read the alembic traceback from the script/workflow output.
3. Fix-forward via a new commit on `main` (preferred), or revert the bad
   migration on `main`. Do **not** edit migration files on the server.
4. Re-deploy:
   ```bash
   /srv/voxel-ledger/deploy.sh
   ```
5. If the bad migration partially applied (data steps before a failing DDL),
   you may need a `downgrade`:
   ```bash
   cd /srv/voxel-ledger/repo
   scripts/web02-compose.sh run --rm backend alembic downgrade -1
   ```
   Then re-deploy.

If migrations succeeded but rebuild left the stack in a half-up state, follow
rollback below — don't try to limp the new image along.

## Rollback to a prior image

When a deploy went out, started, and is misbehaving in a way you can't quickly
fix forward:

1. Identify a known-good commit:
   ```bash
   cd /srv/voxel-ledger/repo
   git log --oneline -10
   ```

2. Check it out:
   ```bash
   git checkout <sha>
   ```

3. Rebuild and rotate:
   ```bash
   scripts/web02-compose.sh up -d --build
   ```

4. Verify:
   ```bash
   scripts/web02-compose.sh ps
   curl -fsS http://127.0.0.1/health
   curl -I http://127.0.0.1/
   ```

5. If the bad deploy ran a schema migration that the rollback target can't
   tolerate, you'll also need to:
   ```bash
   scripts/web02-compose.sh run --rm backend alembic downgrade <target_revision>
   ```
   Migration files live in `backend/alembic/versions/`; cross-reference
   `down_revision` to find the right target.

6. Once stable, push a fix on `main` and re-deploy normally so the checkout
   isn't sitting on a detached HEAD.

> **Backup first when in doubt.** If the rollback requires a downgrade you're
> not confident about, snapshot Postgres before doing it:
> ```bash
> docker exec 3d-print-sales-db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
>   > /srv/voxel-ledger/backups/manual-$(date -u +%Y%m%dT%H%M%SZ).sql
> ```
> (Container name is `3d-print-sales-db` for historical reasons — see
> [docker-compose.prod.yml](../docker-compose.prod.yml).)

## Post-deploy checks (always)

```bash
cd /srv/voxel-ledger/repo
scripts/web02-compose.sh ps
curl -fsS http://127.0.0.1/health
curl -I http://127.0.0.1/
```

Then run a real smoke check from a browser before declaring the deploy live.

## Don't do this without thinking

- `scripts/web02-compose.sh down -v` — destroys named volumes.
- `docker system prune -af --volumes` — same hazard, broader blast radius.
- `git reset --hard` or `git clean -fd` on the host checkout — fine on a
  freshly-deployed clean state, dangerous if anyone's been poking at files.
- `alembic downgrade base` — only ever as part of a tested restore drill.
- Editing files under `/srv/voxel-ledger/repo/` directly. Push to `main`,
  re-deploy. The server checkout should always match a real commit on the
  remote.
