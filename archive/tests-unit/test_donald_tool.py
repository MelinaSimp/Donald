"""Unit tests for the donald read-only Supabase tool.

These run without a live database: the pure helpers (validate_sql,
_json_safe, _row_to_dict) are tested directly, and the async actions are
tested with ``_fetch`` monkeypatched to a fake.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest

from trillion.tools.donald_tool import (
    MAX_ROWS,
    QueryDonaldTool,
    SQLValidationError,
    _json_safe,
    _row_to_dict,
    validate_sql,
)


# --- validate_sql ----------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select count(*) from widgets",
        "WITH t AS (SELECT 1) SELECT * FROM t",
        "  SELECT 1  ",
        "SELECT 1;",
        "SELECT 1 -- a trailing comment\n",
    ],
)
def test_validate_sql_accepts_read_only(sql):
    assert validate_sql(sql) == sql.strip()


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "ALTER TABLE t ADD COLUMN x int",
        "SELECT 1; DROP TABLE t",
        "SELECT 1; SELECT 2",
        "/* hide */ DELETE FROM t",
        "SELECT 1 -- ;DROP\n; DROP TABLE t",
    ],
)
def test_validate_sql_rejects_writes_and_chaining(sql):
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


# --- _json_safe ------------------------------------------------------------

def test_json_safe_scalars_pass_through():
    assert _json_safe(None) is None
    assert _json_safe(True) is True
    assert _json_safe(3) == 3
    assert _json_safe(2.5) == 2.5
    assert _json_safe("x") == "x"


def test_json_safe_complex_types():
    assert _json_safe(datetime(2026, 6, 25, 12, 0, 0)) == "2026-06-25T12:00:00"
    assert _json_safe(Decimal("10")) == 10
    assert isinstance(_json_safe(Decimal("10")), int)
    assert _json_safe(Decimal("1.5")) == 1.5
    assert _json_safe(UUID("12345678-1234-5678-1234-567812345678")) == (
        "12345678-1234-5678-1234-567812345678"
    )
    assert _json_safe(b"\x00\xff") == "00ff"


def test_json_safe_nested():
    assert _json_safe([Decimal("1"), {"k": UUID(int=0)}]) == [
        1,
        {"k": "00000000-0000-0000-0000-000000000000"},
    ]


def test_row_to_dict():
    assert _row_to_dict({"a": Decimal("2"), "b": None}) == {"a": 2, "b": None}


# --- tool wiring -----------------------------------------------------------

def test_requires_dsn():
    with pytest.raises(ValueError):
        QueryDonaldTool("")


def test_definition_shape():
    tool = QueryDonaldTool("postgresql://u:p@h:6543/postgres")
    d = tool.definition()
    assert d["name"] == "query_donald"
    assert d["input_schema"]["required"] == ["action"]
    assert set(d["input_schema"]["properties"]["action"]["enum"]) == {
        "query",
        "list_tables",
        "describe_table",
    }


def _tool_with_fetch(rows_by_call):
    """Build a tool whose _fetch returns canned rows and records calls."""
    tool = QueryDonaldTool("postgresql://u:p@h:6543/postgres")
    calls = []

    async def fake_fetch(sql, args=None):
        calls.append((sql, args))
        return rows_by_call

    tool._fetch = fake_fetch  # type: ignore[method-assign]
    return tool, calls


# --- async actions ---------------------------------------------------------

async def test_query_returns_rows():
    tool, calls = _tool_with_fetch([{"n": Decimal("42")}])
    result = await tool.execute(action="query", sql="SELECT count(*) AS n FROM t")
    assert result == {"rows": [{"n": 42}], "row_count": 1, "truncated": False}
    assert calls[0][0] == "SELECT count(*) AS n FROM t"


async def test_query_rejects_non_select():
    tool, _ = _tool_with_fetch([])
    with pytest.raises(SQLValidationError):
        await tool.execute(action="query", sql="DELETE FROM t")


async def test_query_caps_rows():
    rows = [{"i": i} for i in range(MAX_ROWS + 5)]
    tool, _ = _tool_with_fetch(rows)
    result = await tool.execute(action="query", sql="SELECT i FROM t")
    assert result["row_count"] == MAX_ROWS
    assert result["truncated"] is True


async def test_list_tables():
    tool, calls = _tool_with_fetch([{"table_name": "b"}, {"table_name": "a"}])
    result = await tool.execute(action="list_tables")
    assert result == {"tables": ["b", "a"]}
    assert "information_schema.tables" in calls[0][0]


async def test_describe_table():
    rows = [{"column_name": "id", "data_type": "uuid", "is_nullable": "NO"}]
    tool, calls = _tool_with_fetch(rows)
    result = await tool.execute(action="describe_table", table="widgets")
    assert result["table"] == "widgets"
    assert result["columns"] == rows
    assert calls[0][1] == ["public", "widgets"]


async def test_describe_table_rejects_bad_identifier():
    tool, _ = _tool_with_fetch([])
    with pytest.raises(ValueError):
        await tool.execute(action="describe_table", table="bad; drop")


async def test_unknown_action():
    tool, _ = _tool_with_fetch([])
    with pytest.raises(ValueError):
        await tool.execute(action="nope")
