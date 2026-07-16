-- Initial schema for the Agent Factory.
--
-- Three tables:
--   research_reports  cached Skills Reports (24h dedup on normalized query)
--   spawn_tasks       in-flight spawn pipeline state
--   spawned_agents    the registered, dispatchable agents (pure config rows)

CREATE TABLE IF NOT EXISTS research_reports (
    id               TEXT PRIMARY KEY,
    query            TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    report_json      TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_norm
    ON research_reports (normalized_query, created_at);

CREATE TABLE IF NOT EXISTS spawn_tasks (
    id                  TEXT PRIMARY KEY,
    requested_by        TEXT NOT NULL,
    name_hint           TEXT NOT NULL,
    role_description    TEXT NOT NULL,
    special_requirements TEXT,
    status              TEXT NOT NULL,
    research_report_id  TEXT,
    proposed_manifest   TEXT,           -- JSON, nullable
    approval_iterations INTEGER NOT NULL DEFAULT 0,
    revision_feedback   TEXT,
    error               TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (research_report_id) REFERENCES research_reports (id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON spawn_tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_requested_by ON spawn_tasks (requested_by, created_at);

CREATE TABLE IF NOT EXISTS spawned_agents (
    id                 TEXT PRIMARY KEY,
    slug               TEXT NOT NULL UNIQUE,   -- DB-level guard against collisions
    name               TEXT NOT NULL,
    specialty          TEXT NOT NULL,
    system_prompt      TEXT NOT NULL,
    tool_allowlist     TEXT NOT NULL,          -- JSON array
    model              TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'active',
    created_by_task_id TEXT,
    created_at         TEXT NOT NULL,
    FOREIGN KEY (created_by_task_id) REFERENCES spawn_tasks (id)
);

CREATE INDEX IF NOT EXISTS idx_agents_status ON spawned_agents (status);
