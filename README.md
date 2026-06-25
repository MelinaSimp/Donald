# Donald

Project repository.

## Cloud Postgres setup (hybrid)

The assistant's database can run on a DigitalOcean Droplet so memory is identical
across every device, while the app keeps the ability to fall back to a local
Postgres instantly.

| Item | Value |
| --- | --- |
| Droplet | Ubuntu 24.04 LTS, Basic 2 GB / 1 vCPU (bare IP, no domain) |
| Database name | `assistant` |
| DB role | `assistant_app` |
| Password location | **Your password manager** — never in this repo or chat |
| TLS | Self-signed cert on the droplet; client uses `sslmode=require` |
| Firewall | UFW: port 22 (anywhere) + 5432 (your home IP only) |

**Connection string template** (password redacted — fill from your password manager):

```
postgresql://assistant_app:<PASSWORD>@<DROPLET_IP>:5432/assistant?sslmode=require
```

### Files

| Path | Purpose |
| --- | --- |
| `docs/cloud-postgres-migration.md` | Full step-by-step runbook (Phases 1–7) |
| `scripts/01-harden-droplet.sh` | Non-root user, UFW, unattended-upgrades |
| `scripts/02-setup-postgres.sh` | Install PG (PGDG), TLS, scram, hostssl, random password |
| `scripts/03-migrate-data.sh` | Non-destructive dump → restore → row-count verify |
| `examples/db.py` | Python/FastAPI connection layer with the local↔cloud flag |
| `examples/.env.example` | Environment variables for both modes |

### Rollback

Set `DB_MODE=local` and restart the app to return to the local database
instantly. The local DB is never dropped during migration.

> The live steps (provision, harden, `psql` test) run in **your** terminal. The
> scripts generate the DB password **on the droplet** and never echo it again —
> copy it straight into your password manager.

See `docs/cloud-postgres-migration.md` for the complete procedure.
