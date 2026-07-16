-- M1 foundation schema — accounts, auth sessions, encrypted integration
-- tokens, and agent-run history. Written portably (TEXT ids/timestamps,
-- INTEGER booleans) so it runs on SQLite for dev/tests and Postgres in prod.
-- pgvector/memory tables (M2) land in a later migration.

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL DEFAULT '',
    password_hash   TEXT NOT NULL,
    country         TEXT,
    dob             TEXT,
    tos_accepted_at TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    id         TEXT PRIMARY KEY,
    owner_id   TEXT NOT NULL REFERENCES users(id),
    name       TEXT NOT NULL DEFAULT 'Personal',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

-- One row per issued bearer token. We store only a SHA-256 of the secret, so a
-- database leak never yields a usable token.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- Per-user, per-provider OAuth/API tokens. The secret payload is Fernet-
-- encrypted (see backend/crypto.py); only the ciphertext is stored.
CREATE TABLE IF NOT EXISTS integration_tokens (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id),
    provider   TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_inttok_user ON integration_tokens(user_id);

CREATE TABLE IF NOT EXISTS agent_runs (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    workspace_id TEXT REFERENCES workspaces(id),
    status       TEXT NOT NULL DEFAULT 'running',
    summary      TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    ended_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_user ON agent_runs(user_id);
