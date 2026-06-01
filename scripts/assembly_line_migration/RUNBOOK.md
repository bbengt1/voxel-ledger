# Assembly-line migration — cutover runbook (epic #267, Phase 7)

How to move live production data onto the **Materials → Parts → Products**
model using the Phase 7a backfill engine + the Phase 7b reconciliation
report. **Read this whole file before touching prod.**

The backfill is in-place, dry-run-first, idempotent, **reversible**, and
**non-destructive** (it writes zero inventory transactions and deletes
nothing — material BOM lines are *flagged*, not removed). That makes the
cutover low-risk, but the rehearsal-on-a-restored-snapshot step below is
still mandatory.

## Locked decisions
- On-hand parity is a **hard** invariant (cutover aborts on any drift).
- Product-cost moves up to **±$0.01** are accepted silently; larger moves
  are surfaced for sign-off (expected — direct-material lines become
  part-mediated).
- Cutover is a brief **maintenance window** running `--commit` on prod.
- Reconciliation exiting non-zero (a hard failure) **aborts** the cutover
  before any smoke test.

## Execution mechanism
The repo-root `scripts/` package is **not** baked into the backend image,
so the tool is staged into the running backend container with `docker cp`
and run with the app's interpreter `/opt/venv/bin/python`. (Validated in
7a.) Define once on web02:

```sh
BE=3d-print-sales-backend
stage() { docker cp /srv/voxel-ledger/repo/scripts/. "$BE":/app/scripts/; }
alm()   { docker exec "$BE" sh -lc "cd /app && /opt/venv/bin/python -m scripts.assembly_line_migration $*"; }
unstage(){ docker exec -u 0 "$BE" sh -lc 'cd /app/scripts && rm -rf assembly_line_migration v1_migration *.py __pycache__'; }
```

`alm` inherits the container's `DATABASE_URL` (prod). Re-run `stage` after
any deploy (it recreates the container).

---

## 0. Backup (always first)
```sh
TS=$(date +%Y%m%d-%H%M%S); OUT=/srv/voxel-ledger/backups/voxel_ledger_${TS}.dump
docker exec 3d-print-sales-db sh -lc 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc' > "$OUT"
docker cp "$OUT" 3d-print-sales-db:/tmp/verify.dump \
  && docker exec 3d-print-sales-db pg_restore --list /tmp/verify.dump >/dev/null \
  && echo "backup OK: $OUT" && sha256sum "$OUT" | tee "$OUT.sha256"
```
Never `docker compose down -v`. (NB: feed `pg_restore` a real file path, not
stdin — piping mangles the custom-format header.)

## 1. Rehearse on a restored snapshot (the gate)
Restore the latest dump into a **scratch** database and run the full flow
there. Target: a throwaway DB on the same Postgres container (e.g.
`voxel_rehearsal`) — never the live DB.

```sh
docker exec 3d-print-sales-db sh -lc 'createdb -U $POSTGRES_USER voxel_rehearsal'
docker cp /srv/voxel-ledger/backups/<dump> 3d-print-sales-db:/tmp/r.dump
docker exec 3d-print-sales-db sh -lc 'pg_restore -U $POSTGRES_USER -d voxel_rehearsal /tmp/r.dump'
```

Point the tool at the scratch DB (override `DATABASE_URL` in the `alm`
exec), then:

```sh
stage
alm --capture-baseline ops/al_baseline.json   # before
alm                                            # dry-run: review the plan + review list
alm --commit                                   # apply on the scratch DB
alm --reconcile ops/al_baseline.json           # must print PASS / exit 0
```

Work the dry-run **review list** + reconciliation **coverage/cost** items
with the owner. Iterate (`--reverse --commit` to reset the scratch DB, or
re-restore) until: reconciliation is **PASS**, the review list is
understood/accepted, and cost diffs are signed off. **Do not proceed
until this is clean.**

Drop the scratch DB when done: `docker exec 3d-print-sales-db sh -lc 'dropdb -U $POSTGRES_USER voxel_rehearsal'`.

## 2. Cutover (maintenance window)
1. Announce the window; stop write traffic if practical.
2. **Fresh backup** (step 0) — this is the rollback point.
3. `stage` (if not already), then on the **prod** DB:
   ```sh
   alm --capture-baseline ops/al_cutover_baseline.json
   alm                       # final dry-run sanity check
   alm --commit              # apply
   alm --reconcile ops/al_cutover_baseline.json
   ```
4. **If reconcile exits non-zero → STOP and roll back (step 3a).** Do not
   smoke-test a failed migration.
5. Smoke-test: parts catalog lists `PART-MIG-*`; open a product → its part
   BOM; create + complete a small Build; ring a sale. Confirm health 200.
6. `unstage` to leave the container pristine.

## 3. Rollback
- **3a. Clean-but-wrong** (reconcile PASSED but a human rejects the result):
  use the scripted inverse — it un-points jobs, drops migration part BOM
  lines, and deletes the `PART-MIG-*` parts:
  ```sh
  alm --reverse              # dry-run preview
  alm --reverse --commit     # undo
  ```
- **3b. Corrupt / hard-failure / partial**: restore the step-2 backup.
  ```sh
  docker cp /srv/voxel-ledger/backups/<cutover-dump> 3d-print-sales-db:/tmp/rb.dump
  docker exec 3d-print-sales-db pg_restore --list /tmp/rb.dump >/dev/null   # verify first
  docker exec 3d-print-sales-db sh -lc 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists /tmp/rb.dump'
  ```
  Then restart the stack and confirm health.

## Decision tree
```
reconcile after --commit
├─ exit 0 (PASS) ─ human review of cost diffs / review list
│   ├─ accepted     → smoke-test → done
│   └─ rejected     → 3a scripted --reverse
└─ exit != 0 (HARD) → 3b restore from backup  (never ship a hard failure)
```

The backfill itself never moves inventory, so a hard failure means
something external changed mid-run — restore, investigate, retry in a
fresh window.
