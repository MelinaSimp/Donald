# Backend (M1) — accounts, auth, integration tokens

The multi-tenant product API: signup/login, per-user **encrypted** integration
tokens, and agent-run history. This is roadmap milestone **M1** — the gate the
desktop shell (M3), the OAuth broker (M4), and semantic memory (M2) all build on.

**Multi-tenant by construction:** every repository method that touches user data
takes a `user_id` and filters on it, and every API route depends on
`current_user` (resolved from the bearer token). There is no code path that
returns one user's tokens, runs, or sessions to another.

## Run it

```bash
pip install -r requirements.txt        # fastapi, uvicorn, cryptography, ...
uvicorn "backend.api:create_app" --factory --reload
# -> http://127.0.0.1:8000  (GET /health)
```

Dev uses SQLite at `./donald_data/backend.db` automatically. For Postgres, set
`DATABASE_URL` (and install the driver: `pip install "psycopg[binary]"`).

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/donald
export BACKEND_SECRET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

Migrations in `backend/migrations/*.sql` run automatically on first `open_db()`
and are tracked in a `_migrations` table, so startup is idempotent.

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET  | `/health` | — | Liveness + which DB engine is active |
| POST | `/auth/signup` | — | Create account (email, password, display_name, country, dob, accept_tos) → `{token, user}` |
| POST | `/auth/login` | — | `{token, user}` |
| GET  | `/auth/me` | bearer | Current user |
| POST | `/auth/logout` | bearer | Revoke the presented token |
| GET  | `/integrations` | bearer | Providers this user has connected |
| PUT  | `/integrations/{provider}` | bearer | Store an encrypted token payload |
| DELETE | `/integrations/{provider}` | bearer | Disconnect a provider |
| GET  | `/runs` | bearer | This user's agent-run history |

Auth is a browser/desktop-friendly opaque bearer token: `Authorization: Bearer <token>`.

## Security

- **Passwords** — stdlib `scrypt` (memory-hard), random per-password salt, cost
  parameters stored with the hash, constant-time verify. No plaintext, ever.
- **Session tokens** — 256-bit random, stored only as a SHA-256 hash, with expiry
  and revocation. A DB leak yields no usable token.
- **Integration tokens** — Fernet (AES-128-CBC + HMAC) encrypted with
  `BACKEND_SECRET_KEY` before they touch the DB. A leak yields ciphertext.
- **Isolation** — enforced at the repository layer, not just the route layer
  (see `tests/test_backend.py::test_isolation_at_repo_layer`).

## Layout

| File | Role |
|------|------|
| `db.py` | Connection + migration runner; SQLite / Postgres by `DATABASE_URL` |
| `migrations/` | Portable schema (`001_init.sql`) |
| `crypto.py` | `TokenCipher` — Fernet at-rest encryption for tokens |
| `passwords.py` | scrypt hash/verify |
| `repo.py` | `UserRepo` / `SessionRepo` / `TokenRepo` / `RunRepo` (the isolation boundary) |
| `api.py` | FastAPI app + `current_user` bearer dependency |

## Next (not yet here)

- Wire `RunRepo` into the gateway's agent loop so runs are recorded per user.
- Rate-limit `/auth/*` (reuse `security/auth_ratelimit.py`).
- OAuth **refresh** handling on `TokenRepo` (M4 broker).
- `memory_*` tables + pgvector (M2).
