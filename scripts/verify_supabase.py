"""Verify a read-only Supabase connection before (or after) wiring a tool.

Usage (Doppler injects the env var):

    doppler run -p trillion -c dev -- \\
        uv run python scripts/verify_supabase.py SUPABASE_DONALD_URL

    # also dump every public table's columns (for the schema doc, Step 6):
    doppler run -p trillion -c dev -- \\
        uv run python scripts/verify_supabase.py SUPABASE_DONALD_URL --describe-all

Prints OK + the connected role and table list on success. On failure it prints
the real exception type and message (truncated) — match it against the
playbook's Step-4 decision tree (gaierror = IPv6-only host, InvalidPassword,
InvalidAuthorizationSpecification = wrong username, permission denied = missing
GRANT).

Never paste the connection URL itself into chat — this reads it from the
environment and never echoes it.
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _run(var: str, describe_all: bool) -> int:
    import asyncpg

    url = os.environ.get(var)
    if not url:
        print(f"FAIL: env var {var} is not set (is Doppler injecting it?)")
        return 2
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(url, statement_cache_size=0), timeout=10
        )
    except Exception as e:  # noqa: BLE001 — surface the real error verbatim
        print(f"FAIL ({type(e).__name__}): {str(e)[:250]}")
        return 1

    try:
        row = await conn.fetchrow("SELECT current_user AS role, now() AS ts")
        print("OK:", dict(row))
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        names = [t["table_name"] for t in tables]
        print("Tables:", names)

        if describe_all:
            for name in names:
                cols = await conn.fetch(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = $1 "
                    "ORDER BY ordinal_position",
                    name,
                )
                print(f"\n### {name}")
                for c in cols:
                    null = "NULL" if c["is_nullable"] == "YES" else "NOT NULL"
                    print(f"  - {c['column_name']}: {c['data_type']} {null}")
    finally:
        await conn.close()
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(_run(args[0], describe_all="--describe-all" in flags))


if __name__ == "__main__":
    raise SystemExit(main())
