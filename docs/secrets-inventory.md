# Secrets Inventory (2.4 token-scope minimisation)

> One row per credential the agent holds. Records the **minimum** scope each
> needs so future-you never regenerates at a broader scope. Update the
> `token_scope_audited` attestation in the audit shield once this is complete.

| Env var | Provider | Minimum scope needed | Current scope | Rotated | Notes |
|---|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic | model invocation | — | — | rotate quarterly |
| `AGENT_BEARER_TOKEN` | self | n/a (random 32+ bytes) | — | — | rotate via overlap (2.1) |
| `GITHUB_TOKEN` | GitHub | fine-grained, repo-scoped: Contents:Read, Metadata:Read, Pull requests:Read, Actions:Read | — | — | switch classic → fine-grained |
| `STRIPE_API_KEY` | Stripe | restricted key, read-only scopes used by the agent | — | — | not the full secret key |
| `DATABASE_URL` | Postgres | least-priv app role | — | — | also provision read-only (2.5) |
| `DATABASE_URL_READONLY` | Postgres | SELECT only, CONNECTION LIMIT 5, statement_timeout 30s | — | — | role exists ≠ wired |

## Rotation procedure (per credential)

1. Generate a new credential in the provider console with **minimal** scopes.
2. `<secrets CLI> secrets set NAME=<new_value>` in dev + prod.
3. Restart the agent.
4. Verify the relevant agent flow still works.
5. **Revoke the old credential in the provider console.** Without revocation,
   the rotation gives you nothing.

## Database read-only role (2.5)

```sql
CREATE ROLE agent_readonly LOGIN PASSWORD '<set-in-secrets-manager>'
  CONNECTION LIMIT 5;
GRANT CONNECT ON DATABASE <db> TO agent_readonly;
GRANT USAGE ON SCHEMA public TO agent_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_readonly;
ALTER ROLE agent_readonly SET statement_timeout = '30s';
```

Verify the role can `SELECT` but **cannot** `INSERT` / `UPDATE` / `DELETE`,
then store the read-only DSN in the secrets manager (never in code or repo).
The role's mere existence is the win; wiring code paths to it is a separate
opt-in refactor.
