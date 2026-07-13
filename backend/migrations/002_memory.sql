-- M2 memory tiers. One table holds all durable memory items, discriminated by
-- `kind`: 'fact' (structured profile), 'chunk' (semantic RAG over
-- conversations/files/notes), 'episode' (per-session summaries). Embeddings are
-- stored portably as a JSON array of floats so this runs unchanged on SQLite and
-- Postgres; cosine ranking is computed in Python over a user's (bounded) items.
--
-- pgvector upgrade path (Postgres, when recall volume demands it):
--   CREATE EXTENSION IF NOT EXISTS vector;
--   ALTER TABLE memory_items ADD COLUMN embedding_vec vector(256);
--   CREATE INDEX ON memory_items USING ivfflat (embedding_vec vector_cosine_ops);
-- then rank with `ORDER BY embedding_vec <=> :query` instead of in Python.

CREATE TABLE IF NOT EXISTS memory_items (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id),
    kind       TEXT NOT NULL,                 -- 'fact' | 'chunk' | 'episode'
    content    TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    source     TEXT,                          -- 'conversation' | 'file:...' | run_id
    embedding  TEXT NOT NULL,                 -- JSON array of floats
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_user_kind ON memory_items(user_id, kind);
