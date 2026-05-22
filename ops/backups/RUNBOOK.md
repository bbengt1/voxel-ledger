# Backup + restore runbook (Phase 12.2, #204)

> **Targets:** RPO ≤ 24 h, RTO ≤ 2 h. The drill in `drill.sh` is what
> gates that claim.

## 1. What's protected

| Asset | How |
| --- | --- |
| Postgres data | Nightly `pg_basebackup` tarball (`backup.sh`) + continuous WAL archive (`postgresql.archive.conf`) |
| Attachments | Nightly `rsync` (`attachments_mirror.sh`) — bandwidth-throttled |
| Application code | Git remote (no separate backup) |
| `.env` / secrets | Operator's password manager — **not** in this repo |

## 2. Scheduling on web01

`backup.sh` + `attachments_mirror.sh` run from a systemd timer.

```
# /etc/systemd/system/voxel-backup.service
[Service]
Type=oneshot
User=postgres
EnvironmentFile=/srv/3d-print-sales/env/web01.env
ExecStart=/srv/3d-print-sales/repo/ops/backups/backup.sh
ExecStart=/srv/3d-print-sales/repo/ops/backups/attachments_mirror.sh

# /etc/systemd/system/voxel-backup.timer
[Timer]
OnCalendar=*-*-* 03:30:00 UTC
Persistent=true
```

`web01.env` provides:

```
PGHOST=db
PGPORT=5432
PGUSER=voxel
PGPASSWORD=...
BACKUP_ROOT=/srv/3d-print-sales/backups
OFFSITE_RSYNC=user@offsite.example.com:/srv/voxel-backups/
ATTACHMENTS_STORAGE_ROOT=/srv/3d-print-sales/data/attachments
```

## 3. WAL archiving

The compose Postgres image mounts
`ops/backups/postgresql.archive.conf` via `-c
config_file=/etc/postgresql/postgresql.conf` (production manifest)
and writes WAL segments to `/var/backups/wal/`. The same systemd
timer that runs `backup.sh` ships those segments off-site:

```
ExecStart=/usr/bin/rsync -a --remove-source-files \
  /var/backups/wal/ user@offsite.example.com:/srv/voxel-wal/
```

`archive_command` is idempotent (`test ! -f && cp`) so a re-runs
don't double-write.

## 4. Restore (real incident)

Worst case: the production DB is unrecoverable. We have a base
backup from N hours ago + WAL segments since.

```bash
# On a fresh VM with Postgres 16 installed and the data dir empty.
TARGET_TIME="2026-05-21 16:42:00 UTC"          # how far forward to replay
BASE=/srv/voxel-restore/base-20260521T033000Z  # latest base from offsite
WAL=/srv/voxel-restore/wal

systemctl stop postgresql

# 1. Lay down the base backup.
sudo -u postgres tar -xzf "${BASE}/base/base.tar.gz" -C /var/lib/postgresql/16/main

# 2. Configure recovery.
sudo -u postgres tee /var/lib/postgresql/16/main/postgresql.auto.conf <<EOF
restore_command = 'cp ${WAL}/%f %p'
recovery_target_time = '${TARGET_TIME}'
recovery_target_action = 'promote'
EOF
sudo -u postgres touch /var/lib/postgresql/16/main/recovery.signal

# 3. Start. Postgres replays WAL up to TARGET_TIME, promotes, drops
#    the signal file.
systemctl start postgresql

# 4. Smoke checks.
sudo -u postgres psql voxel_ledger -c "SELECT COUNT(*) FROM event;"
sudo -u postgres psql voxel_ledger -c "SELECT MAX(position) FROM event;"
sudo -u postgres psql voxel_ledger -c "SELECT event_hash FROM event ORDER BY position DESC LIMIT 1;"

# 5. Restore attachments.
rsync -a --info=progress2 \
  user@offsite.example.com:/srv/voxel/attachments/ \
  /srv/3d-print-sales/data/attachments/

# 6. Re-point the app and bring it up.
cd /srv/3d-print-sales/repo
/srv/3d-print-sales/deploy.sh
```

Hit the documented post-deploy smoke endpoints
(`/health`, `/api/v1/dashboard/kpis`, `/api/v1/control-center`) and
verify the latest known invoice number is present.

## 5. Drill (rehearsal)

Two modes, both run in CI on every PR:

- **`drill.sh smoke`** — `pg_dump` → `pg_restore` round-trip against a
  source DB. Proves the schema + data payload survives a logical
  dump. Used as the per-PR data-payload gate.
- **`drill.sh full`** — end-to-end `pg_basebackup` + WAL archive +
  point-in-time restore. Self-contained: launches its own primary +
  target Postgres containers via Docker, writes a synthetic event
  table, takes a base, writes *more* rows, captures
  `pg_current_wal_lsn()` as the recovery target, then verifies the
  post-base rows replay in. Validates the OPS MECHANICS
  (archive_command, restore_command, recovery_target_lsn,
  promotion).

```bash
# Smoke mode (data-payload round-trip).
DRILL_SRC_URL="postgres://voxel:voxel@localhost:5432/voxel_ledger" \
  ops/backups/drill.sh smoke

# Full mode (WAL-replay + PITR).
DRILL_DST_PORT=5601 ops/backups/drill.sh full
```

A real on-host drill (twice a year, scheduled):

```bash
# 1. Pull the latest offsite base + a few hours of WAL.
# 2. Run §4 against a fresh VM (or a sandbox postgres on web01).
# 3. Record the elapsed time; assert < RTO budget.
# 4. Run drill.sh smoke against the restored DB to assert parity.
# 5. Tear down.
```

## 6. Limits + follow-ups

- The S3-flavored offsite path (rclone / restic) is not wired
  here; the runbook uses `rsync` over SSH because that's what
  web01 currently has.
- Encryption-at-rest for offsite backups is a separate concern;
  use SSH transport + filesystem-encrypted offsite host until a
  per-backup encryption layer lands.
