# donald — Supabase schema (read-only)

> **STATUS: NOT YET POPULATED FROM A LIVE DATABASE.**
> This file was scaffolded in a sandbox with no DB access. The columns and
> examples below are placeholders. Per the playbook, **do not guess column
> names** — fill the tables in from the live `list_tables` / `describe_table`
> output (commands at the bottom) before relying on this doc, then delete this
> banner and set the verification date.

**Verification date:** _not yet verified_
**Tool:** `query_donald` &nbsp;•&nbsp; **Env var:** `SUPABASE_DONALD_URL`
**Role:** `trillion_analytics` (SELECT-only, `statement_timeout = 5s`)

---

## Critical gotchas

> Fill this in first — it pays for itself. List the non-obvious translations
> between how the user speaks and what the schema actually contains. Examples
> of the *kind* of thing that goes here (replace with real ones):
>
> - When the user says "_<domain word>_", they mean table `<table>`, column `<column>`.
> - Money is stored in `<unit>` (e.g. cents) — divide by 100 for dollars.
> - Status enum values are `<...>`; "active" means `status = '<...>'`.
> - Timestamps are UTC (`timestamptz`); convert before quoting times to the user.

---

## Tables

> One subsection per table, copied verbatim from `describe_table`. Keep the
> public schema only — never document or query `auth.*` or other private
> schemas.

### `<table_name>`

| column | type | nullable |
| ------ | ---- | -------- |
| _fill from describe_table_ | | |

---

## Worked query examples

> 5–10 examples phrased the way the user actually asks, each with the SQL the
> tool should run. Replace the stubs once columns are known.

1. **"How many _<things>_ do we have?"**
   ```sql
   SELECT count(*) AS n FROM <table>;
   ```

2. **"_<question>_"**
   ```sql
   -- SELECT ...
   ```

_(add 3–8 more covering the real questions the user will ask)_

---

## How to populate this doc (run against the live DB)

With `SUPABASE_DONALD_URL` set in Doppler:

```bash
doppler run -p trillion -c dev -- uv run python scripts/verify_supabase.py SUPABASE_DONALD_URL --describe-all
```

That prints every public table and its columns/types/nullability — paste the
output into the sections above. Then update the verification date and remove
the status banner.
