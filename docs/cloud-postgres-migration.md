# Cloud Postgres Migration Runbook

Migrate the assistant's **local Postgres** to a **hybrid setup** where the
database lives on a DigitalOcean Droplet, so the assistant remembers you
identically across every device.

> **Your setup (locked in):** Python + FastAPI app · existing local data to keep
> · DigitalOcean account + SSH key already uploaded · **bare IP** (no domain) →
> self-signed TLS, `sslmode=require`.

## Conventions used below

Set these in *your* shell before running commands. Replace the placeholders.

```bash
export DROPLET_IP="203.0.113.10"        # your droplet's public IPv4
export ADMIN_USER="deploy"              # the non-root sudo user you'll create
export HOME_IP="$(curl -s https://ifconfig.me)"  # your current public IP (UFW allowlist)
export APP_DB="assistant"               # cloud database name
export APP_DB_USER="assistant_app"      # cloud database role
export LOCAL_DB="assistant"             # your existing local database name
```

> **Hard rules (do not break):**
> - Never paste passwords or SSH keys into chat/commits. Secrets are generated
>   **on the droplet** and copied straight into your password manager.
> - Only ports **22** and **5432** are ever opened.
> - Data migration is **non-destructive**: dump → restore → verify counts. The
>   local DB is kept as a fallback for several days.
> - `psql` from your laptop must succeed **before** any app config changes.
> - Confirm before destructive steps: rebooting, dropping a DB, overwriting config.

---

## Phase 1 — Provision the droplet

Create via the DigitalOcean UI (or `doctl`):

- **Image:** Ubuntu 24.04 LTS
- **Plan:** Basic → Regular Intel, **2 GB RAM / 1 vCPU** (plenty to start)
- **Region:** closest to you (lowest latency to your devices)
- **Authentication:** **SSH key only** (select your already-uploaded key). No password auth.
- **Hostname:** e.g. `assistant-db`

With `doctl` (optional):

```bash
doctl compute droplet create assistant-db \
  --image ubuntu-24-04-x64 \
  --size s-1vcpu-2gb \
  --region nyc1 \
  --ssh-keys "$(doctl compute ssh-key list --format ID --no-header | head -1)" \
  --wait
doctl compute droplet list --format Name,PublicIPv4
```

Confirm you can reach it as root (key auth):

```bash
ssh root@"$DROPLET_IP" 'echo connected as $(whoami)'
```

---

## Phase 2 — Harden the droplet

Copy `scripts/01-harden-droplet.sh` up and run it. It creates the non-root sudo
user, enables UFW (allowing **only** 22 from anywhere and **5432 from your home
IP only**), and turns on `unattended-upgrades`.

```bash
scp scripts/01-harden-droplet.sh root@"$DROPLET_IP":/root/
ssh root@"$DROPLET_IP" "ADMIN_USER='$ADMIN_USER' HOME_IP='$HOME_IP' bash /root/01-harden-droplet.sh"
```

Add your SSH key to the new user, then verify you can log in as them:

```bash
ssh root@"$DROPLET_IP" "mkdir -p /home/$ADMIN_USER/.ssh && cp /root/.ssh/authorized_keys /home/$ADMIN_USER/.ssh/ && chown -R $ADMIN_USER:$ADMIN_USER /home/$ADMIN_USER/.ssh && chmod 700 /home/$ADMIN_USER/.ssh && chmod 600 /home/$ADMIN_USER/.ssh/authorized_keys"
ssh "$ADMIN_USER@$DROPLET_IP" 'sudo ufw status verbose'
```

You should see `22/tcp ALLOW Anywhere` and `5432/tcp ALLOW <your home IP>`.

> ⚠️ **Confirm before reboot.** The harden script does **not** reboot. If a kernel
> update later requires one, do it deliberately and reconnect afterward.

---

## Phase 3 — Install & configure Postgres (TLS, password-only remote)

Copy `scripts/02-setup-postgres.sh` up and run it as the admin user. It:

- installs the latest stable Postgres from the **official PGDG apt repo**,
- creates role `$APP_DB_USER` with a **randomly generated** password
  (printed **once, only in the droplet terminal** — copy it into your password
  manager immediately),
- creates database `$APP_DB` owned by that role,
- generates a **self-signed TLS cert**, sets `ssl = on`,
- sets `listen_addresses = '*'` (safe — UFW is the gatekeeper),
- rewrites `pg_hba.conf` so all remote connections require **`hostssl` + scram password**,
- restarts and verifies Postgres is listening on the public interface.

```bash
scp scripts/02-setup-postgres.sh "$ADMIN_USER@$DROPLET_IP":/tmp/
ssh -t "$ADMIN_USER@$DROPLET_IP" "APP_DB='$APP_DB' APP_DB_USER='$APP_DB_USER' DROPLET_IP='$DROPLET_IP' bash /tmp/02-setup-postgres.sh"
```

> 🔐 **Copy the generated password into your password manager now.** It is never
> echoed again, never written to this repo, never sent to chat.

Verify it is listening publicly:

```bash
ssh "$ADMIN_USER@$DROPLET_IP" "sudo ss -tlnp | grep 5432"
# expect 0.0.0.0:5432 (not just 127.0.0.1)
```

---

## Phase 4 — Test connectivity BEFORE touching app config

From **your laptop** (this must succeed before Phase 5):

```bash
# You'll be prompted for the password you saved in your password manager.
psql "postgresql://$APP_DB_USER@$DROPLET_IP:5432/$APP_DB?sslmode=require" -c '\conninfo'
```

You should see `SSL connection (protocol: TLSv1.3, ...)`. If it hangs → UFW/home-IP
mismatch (your IP changed; re-run the allowlist with the new `HOME_IP`). If it
refuses → `listen_addresses`/restart. Fix before continuing.

---

## Phase 5 — Migrate existing data (non-destructive)

Use `scripts/03-migrate-data.sh`. It dumps your local DB, restores into the cloud
DB, and **compares row counts table-by-table**. It never drops the local DB.

```bash
APP_DB="$APP_DB" APP_DB_USER="$APP_DB_USER" DROPLET_IP="$DROPLET_IP" \
LOCAL_DB="$LOCAL_DB" \
  bash scripts/03-migrate-data.sh
```

Review the printed diff table. Every table's local and cloud counts must match.
**Keep the local DB** as a fallback for at least a few days.

---

## Phase 6 — Point the app at the cloud (behind a flag)

In your **Python/FastAPI app repo** (not this one), adopt the pattern in
`examples/db.py` and `examples/.env.example`:

- All credentials come from **environment variables** — nothing hard-coded.
- `DB_MODE=cloud` builds the cloud DSN with `sslmode=require`; `DB_MODE=local`
  keeps your old local connection working so you can switch back instantly.
- Update your real `.env.example` with the new variables.

Then re-run end-to-end:

```bash
# in the app repo
export DB_MODE=cloud
uvicorn app.main:app --reload   # or however you launch it
```

Trigger something that writes state (a conversation / memory write), then confirm
the row landed in the **cloud** DB:

```bash
psql "postgresql://$APP_DB_USER@$DROPLET_IP:5432/$APP_DB?sslmode=require" \
  -c "SELECT count(*) FROM <your_memory_table>;"
```

Resilience check: drop your network, reconnect, restart the app, confirm state
restores. If you have a second device, point it at the same DSN and confirm it
sees the same memory.

Instant rollback: `export DB_MODE=local` and restart.

---

## Phase 7 — Follow-ups to plan separately

These are **not** covered by this runbook and should be scheduled as their own work:

- Scheduled automated backups (`pg_dump` cron or DO Snapshots / managed backup).
- Off-site backup mirror (e.g. to object storage in a second region).
- Point-in-time recovery (WAL archiving).
- Monitoring & alerts (disk, connections, replication lag, failed logins).
- Secret rotation policy for the DB password.
- Fail2ban / restricting SSH further; consider a VPN/WireGuard instead of a raw
  5432 allowlist if your home IP is dynamic.

---

## Rollback

1. `export DB_MODE=local` in the app and restart → back on local Postgres instantly.
2. The cloud droplet can stay up; no data is lost on either side.
3. The local DB was never dropped, so it is always a clean fallback.
