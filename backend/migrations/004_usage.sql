-- M7 cost guardrail. One row per user per UTC day counts chat turns, so a
-- runaway loop (or an abusive client) can't quietly burn the operator's model
-- credits. Enforced in the gateway before each turn runs.

CREATE TABLE IF NOT EXISTS usage_daily (
    user_id TEXT NOT NULL REFERENCES users(id),
    day     TEXT NOT NULL,                 -- YYYY-MM-DD (UTC)
    turns   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
