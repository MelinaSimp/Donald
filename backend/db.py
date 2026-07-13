"""Database access for the backend — one thin layer over SQLite (dev/tests)
and Postgres (prod), selected by ``DATABASE_URL``.

    postgresql://user:pass@host/db   -> Postgres via psycopg (lazy import)
    sqlite:///path/to/file.db        -> SQLite file
    (unset)                          -> SQLite at ./donald_data/backend.db

The rest of the backend writes portable SQL with ``?`` placeholders; for
Postgres we translate ``?`` -> ``%s`` at execute time. Keeping the SQL portable
is deliberate — the schema (backend/migrations) avoids engine-specific types so
the same statements run on both.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

_MIGRATIONS = Path(__file__).parent / "migrations"


class DB:
    """A minimal connection wrapper with a uniform ``execute`` / ``query`` API.

    Rows come back as dicts regardless of engine, so repositories never depend
    on sqlite3.Row vs psycopg tuples.
    """

    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("DATABASE_URL") or ""
        self.is_postgres = self.url.startswith(("postgres://", "postgresql://"))
        if self.is_postgres:
            import psycopg  # lazy: only needed in prod

            self._conn = psycopg.connect(self.url, autocommit=True)
        else:
            path = self._sqlite_path(self.url)
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _sqlite_path(url: str) -> str:
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///") :]
        if url == "sqlite://:memory:" or url == "sqlite://":
            return ":memory:"
        return str(Path("donald_data") / "backend.db")

    def _adapt(self, sql: str) -> str:
        return re.sub(r"\?", "%s", sql) if self.is_postgres else sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        cur = self._conn.cursor()
        cur.execute(self._adapt(sql), tuple(params))
        if not self.is_postgres:
            self._conn.commit()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(self._adapt(sql), tuple(params))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def executescript(self, script: str) -> None:
        if self.is_postgres:
            self._conn.cursor().execute(script)
        else:
            self._conn.executescript(script)
            self._conn.commit()

    def migrate(self) -> list[str]:
        """Apply every ``NNN_*.sql`` in migrations/ once, in order."""
        self.executescript(
            "CREATE TABLE IF NOT EXISTS _migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {r["name"] for r in self.query("SELECT name FROM _migrations")}
        ran: list[str] = []
        for path in sorted(_MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            self.executescript(path.read_text())
            self.execute(
                "INSERT INTO _migrations (name, applied_at) VALUES (?, ?)",
                (path.name, _now()),
            )
            ran.append(path.name)
        return ran

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def open_db(url: str | None = None, *, migrate: bool = True) -> DB:
    db = DB(url)
    if migrate:
        db.migrate()
    return db
