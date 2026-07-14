-- M5 billing. One subscription row per user, driven by Stripe webhooks. Plan
-- gates feature access; status mirrors Stripe. Portable types (TEXT/JSON), so
-- this runs unchanged on SQLite and Postgres like the rest of the schema.

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                TEXT PRIMARY KEY REFERENCES users(id),
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    plan                   TEXT NOT NULL DEFAULT 'free',      -- 'free' | 'pro'
    status                 TEXT NOT NULL DEFAULT 'inactive',  -- Stripe sub status
    current_period_end     TEXT,
    updated_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_customer ON subscriptions(stripe_customer_id);
