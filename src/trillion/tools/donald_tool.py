"""Read-only Supabase query tool for the ``donald`` project.

This is the CANONICAL TEMPLATE for read-only Supabase integrations in
Trillion. To add another project, copy this file to
``src/trillion/tools/<slug>_tool.py``, rename ``QueryDonaldTool`` /
``query_donald`` / the schema-doc reference, and register it conditionally in
``registry.py`` (see the playbook). Do not refactor a shared base class out
until the 4th Supabase project lands — duplication is fine at N=2/3.

Safety model (defense in depth — both layers matter):

  1. Connection layer (enforced in Supabase, not here): Trillion connects as
     the dedicated ``trillion_analytics`` role, which has SELECT-only grants
     and a short server-side ``statement_timeout``.
  2. Tool layer (this file): :func:`validate_sql` rejects anything that is not
     a single read-only SELECT/WITH statement, and every result set is capped
     at :data:`MAX_ROWS`.

The schema this tool serves is documented in
``context/donald-supabase-schema.md``.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from trillion.tools.base import Tool

logger = logging.getLogger("trillion.tools.donald_tool")

TOOL_NAME = "query_donald"
SCHEMA = "public"
MAX_ROWS = 1000

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LEADING_KEYWORD = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SQLValidationError(ValueError):
    """Raised when a query is not a single read-only SELECT/WITH statement."""


def _strip_comments(sql: str) -> str:
    """Remove block and line comments so they can't smuggle a second statement."""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql


def validate_sql(sql: str) -> str:
    """Return the trimmed SQL if it is a single read-only statement, else raise.

    Allows exactly one statement beginning with SELECT or WITH. Rejects empty
    input, non-query statements, and statement chaining (an embedded ``;``).

    A trailing ``;`` terminator is allowed. As a conservative backstop this
    also rejects a ``;`` inside a string literal — the DB role is SELECT-only
    regardless, so over-rejecting here is safe.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Empty query.")
    cleaned = _strip_comments(sql).strip()
    if not _LEADING_KEYWORD.match(cleaned):
        raise SQLValidationError("Only read-only SELECT / WITH queries are allowed.")
    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    if ";" in body:
        raise SQLValidationError("Statement chaining is not allowed.")
    return sql.strip()


def _json_safe(value: Any) -> Any:
    """Convert a Postgres value into something ``json.dumps`` can handle."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """JSON-safe dict for one asyncpg Record (or any mapping)."""
    return {str(k): _json_safe(v) for k, v in dict(row).items()}


class QueryDonaldTool(Tool):
    """Run read-only SQL against the donald Supabase database."""

    def __init__(self, dsn: str, *, max_rows: int = MAX_ROWS) -> None:
        if not dsn:
            raise ValueError("QueryDonaldTool requires a non-empty asyncpg DSN.")
        self._dsn = dsn
        self._max_rows = max_rows

    def definition(self) -> dict[str, Any]:
        return {
            "name": TOOL_NAME,
            "description": (
                "Query the donald Supabase Postgres database (read-only). Use "
                "this to answer questions about the donald project's data. "
                "Three actions: 'query' runs a single read-only SELECT/WITH "
                "statement (no writes, no statement chaining; results are "
                f"capped at {MAX_ROWS} rows); 'list_tables' lists tables in the "
                "public schema; 'describe_table' returns a table's columns with "
                "types and nullability. See the donald schema doc for column "
                "names and worked examples — do not guess column names."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["query", "list_tables", "describe_table"],
                        "description": "Which operation to perform.",
                    },
                    "sql": {
                        "type": "string",
                        "description": (
                            "Required for action='query'. A single read-only "
                            "SELECT or WITH statement."
                        ),
                    },
                    "table": {
                        "type": "string",
                        "description": (
                            "Required for action='describe_table'. A table name "
                            "in the public schema."
                        ),
                    },
                },
                "required": ["action"],
            },
        }

    async def _fetch(self, sql: str, args: list[Any] | None = None) -> list[Any]:
        """Open a short-lived connection and run one query.

        ``statement_cache_size=0`` is REQUIRED: the Supabase transaction pooler
        does not support prepared-statement caching. Lazy import keeps the pure
        helpers (and their tests) free of the asyncpg dependency.
        """
        import asyncpg

        conn = await asyncpg.connect(self._dsn, statement_cache_size=0)
        try:
            return await conn.fetch(sql, *(args or []))
        finally:
            await conn.close()

    async def execute(self, **params: Any) -> dict[str, Any]:
        action = params.get("action")
        if action == "query":
            return await self._run_query(params.get("sql", ""))
        if action == "list_tables":
            return await self._list_tables()
        if action == "describe_table":
            return await self._describe_table(params.get("table", ""))
        raise ValueError(f"Unknown action: {action!r}")

    async def _run_query(self, sql: str) -> dict[str, Any]:
        validate_sql(sql)
        rows = await self._fetch(sql)
        capped = rows[: self._max_rows]
        return {
            "rows": [_row_to_dict(r) for r in capped],
            "row_count": len(capped),
            "truncated": len(rows) > self._max_rows,
        }

    async def _list_tables(self) -> dict[str, Any]:
        rows = await self._fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = $1 AND table_type = 'BASE TABLE' "
            "ORDER BY table_name",
            [SCHEMA],
        )
        return {"tables": [r["table_name"] for r in rows]}

    async def _describe_table(self, table: str) -> dict[str, Any]:
        if not _IDENTIFIER.match(table or ""):
            raise ValueError(f"Invalid table name: {table!r}")
        rows = await self._fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = $1 AND table_name = $2 "
            "ORDER BY ordinal_position",
            [SCHEMA, table],
        )
        return {"table": table, "columns": [_row_to_dict(r) for r in rows]}
