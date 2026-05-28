# `web02` — first-time host bootstrap

One-time setup to take a fresh `web02.bengtson.local` from "Linux box with SSH"
to "ready for the canonical n8n deploy workflow." Run these steps once; routine
deploys go through [the n8n workflow](web02_n8n_deploy.md) or
[the manual SSH runbook](web02_runbook.md).

- **Host:** `root@web02.bengtson.local`
- **OS assumed:** RHEL/EL10-compatible (the live box reports `el10_1.x86_64`).
- **Repo:** this repository, branch `main`.
- **App root on host:** `/srv/voxel-ledger/`

## 0. Prerequisites

- SSH key-based access for `root` from your workstation. Set up via
  `ssh-copy-id` (see `~/.ssh/config` entry `web02`).
- Outbound internet from web02 (package install, image pulls, `git clone`).
- DNS: `web02.bengtson.local` resolves on the LAN. Cloudflare Tunnel
  fronts the public hostname **https://print.bengtsonprecision3d.com/**
  → `web02:80`. The box itself only serves plain HTTP locally; TLS
  terminates at Cloudflare.

## 1. Install host packages

```bash
ssh web02
# Docker engine + compose plugin via the official repo (preferred on EL10):
dnf -y install dnf-plugins-core
dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Basic tooling.
dnf -y install git curl jq

# Sanity check.
docker version
docker compose version
git --version
```

## 2. Create the app-root layout

```bash
install -d -m 0755 /srv/voxel-ledger
install -d -m 0755 /srv/voxel-ledger/env
install -d -m 0700 /srv/voxel-ledger/data
install -d -m 0700 /srv/voxel-ledger/data/pg
install -d -m 0755 /srv/voxel-ledger/data/attachments
install -d -m 0755 /srv/voxel-ledger/backups
```

Resulting layout:

```
/srv/voxel-ledger/
  repo/                  # git checkout (created in step 3)
  env/web02.env          # secrets — populated in step 4
  data/pg/               # postgres bind-mount
  data/attachments/      # uploads
  backups/               # nightly pg_dump
  deploy.sh              # wrapper, installed in step 5
```

## 3. Clone the repo

```bash
cd /srv/voxel-ledger
git clone https://github.com/<org>/voxel-ledger.git repo
cd repo
git checkout main
```

> If the repo is private, configure a deploy key or HTTPS token before clone.

## 4. Populate the server env file

The repo ships a template at [`.env.web02.example`](../.env.web02.example).
Copy it and fill in real secrets:

```bash
cp /srv/voxel-ledger/repo/.env.web02.example /srv/voxel-ledger/env/web02.env
chown root:root /srv/voxel-ledger/env/web02.env
chmod 600 /srv/voxel-ledger/env/web02.env

# Generate fresh secrets:
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

Then edit `/srv/voxel-ledger/env/web02.env` and replace every `CHANGE-ME` line:

- `JWT_SECRET_KEY` — from the command above.
- `POSTGRES_PASSWORD` and the password inside `DATABASE_URL` — must match.
- `OWNER_EMAIL` / `OWNER_PASSWORD` — initial admin login (used once by the seed
  script on first boot). Change the password from the UI after login.

Do **not** commit the populated file. `.gitignore` and the template comment
both flag this; the file lives outside the repo path anyway.

## 5. Install the host-side deploy wrapper

```bash
cat > /srv/voxel-ledger/deploy.sh <<'EOF'
#!/usr/bin/env bash
# Host-side wrapper. Routes to the repo's deploy script with the right COMPOSE
# wrapper so /srv/voxel-ledger/env/web02.env is picked up.
set -euo pipefail
cd /srv/voxel-ledger/repo
exec env COMPOSE=scripts/web02-compose.sh ./scripts/deploy.sh "$@"
EOF
chmod +x /srv/voxel-ledger/deploy.sh
```

## 6. Install the systemd unit

```bash
cat > /etc/systemd/system/voxel-ledger.service <<'EOF'
[Unit]
Description=Voxel Ledger production stack (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/voxel-ledger/repo
ExecStart=/srv/voxel-ledger/repo/scripts/web02-compose.sh up -d
ExecStop=/srv/voxel-ledger/repo/scripts/web02-compose.sh down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable voxel-ledger.service
```

The unit only **lifts** the stack on boot; it does not rebuild. Routine deploys
go through `/srv/voxel-ledger/deploy.sh` (which rebuilds), not via systemd.

## 7. First deploy

```bash
/srv/voxel-ledger/deploy.sh
```

This runs the full `scripts/deploy.sh` pipeline: fetch + fast-forward → run
all migrations on a fresh DB → build + start containers → poll `/health` →
print `compose ps`.

Expect 3–6 minutes for a cold first build (frontend `pnpm install` + `vite build`
+ backend image build + initial pg setup).

## 8. Verify

```bash
cd /srv/voxel-ledger/repo
scripts/web02-compose.sh ps          # all services Up/healthy
curl -fsS http://127.0.0.1/health    # backend reachable
curl -I http://127.0.0.1/            # frontend served
```

Browser smoke: log in as `OWNER_EMAIL`, change the password, click through the
POS and one report view. Container health is necessary but not sufficient.

## 9. Wire up n8n

Once verified, set up the canonical deploy workflow:
[`docs/web02_n8n_deploy.md`](web02_n8n_deploy.md).

## Troubleshooting

- **`scripts/web02-compose.sh: env file not found`** — step 4 wasn't completed,
  or the file isn't at `/srv/voxel-ledger/env/web02.env`.
- **Backend container restart-loops with a `change-me`/`CHANGE-ME` error** —
  the Settings validator is rejecting placeholder values; finish step 4.
- **`/health` never returns 200** — almost always the backend; tail logs:
  `scripts/web02-compose.sh logs -f --tail=200 backend`. The first start can
  also be slow if migrations are doing real work; allow the 60s polling window.
- **Postgres permission errors on first start** — the `data/pg` directory was
  pre-populated or has the wrong ownership. Stop the stack, `rm -rf data/pg/*`,
  re-create the dir, re-deploy. (Only safe before any real data exists.)
