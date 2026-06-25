# Donald — Trillion read-only Supabase integration

Bootstrap of the Trillion read-only Supabase tool pattern. Trillion answers
questions about a Supabase-backed Postgres database by running **read-only**
SQL through a dedicated `trillion_analytics` role.

## Layout

| Path | Purpose |
| ---- | ------- |
| `src/trillion/config.py` | Settings loaded from env (`SUPABASE_<SLUG>_URL`). |
| `src/trillion/tools/base.py` | `Tool` interface (definition + async execute). |
| `src/trillion/tools/donald_tool.py` | `query_donald` tool — **canonical template** for new Supabase projects. |
| `src/trillion/tools/registry.py` | Conditional tool registration. |
| `tests/unit/` | Unit tests (no DB required). |
| `context/donald-supabase-schema.md` | Schema doc — **populate from a live DB** (see banner). |
| `context/_manifest.toml` | Which docs load into the system prompt. |
| `scripts/verify_supabase.py` | Live connection / schema-dump check. |

## Safety model (defense in depth)

1. **DB layer:** connect as `trillion_analytics` — SELECT-only grants, short
   `statement_timeout`. Never the `postgres` superuser.
2. **Tool layer:** `validate_sql()` allows a single SELECT/WITH statement
   only (no writes, no statement chaining); results capped at 1000 rows.

## Develop

```bash
uv run --extra dev pytest        # run the unit tests
```

## Add another Supabase project

Copy `src/trillion/tools/donald_tool.py` to `<slug>_tool.py`, rename the class
/ tool name / schema-doc reference, register it in `registry.py` behind
`settings.supabase_<slug>_url`, add the field to `config.py`, and write
`context/<slug>-supabase-schema.md`. Don't extract a shared base class until
the 4th project lands.

## Live verification (requires Doppler + the real Supabase project)

```bash
doppler run -p trillion -c dev -- \
    uv run python scripts/verify_supabase.py SUPABASE_DONALD_URL --describe-all
```

Must print `OK:` with the `trillion_analytics` role and a table list before
the tool is trusted. See the Supabase playbook for the full step-by-step
(role creation, the IPv4 pooler connection string, Doppler, end-to-end smoke
test).
