"""SQLite connection + migration runner.

Migrations are plain ``.sql`` files in ``migrations/`` applied in filename
order. A ``schema_migrations`` table records what's been applied so
``migrate()`` is idempotent — re-running it is a no-op. This mirrors the
"raw SQL files + a custom runner" pattern rather than pulling in Alembic for
a SQLite slice.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply any un-applied migration files. Returns the names applied."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    newly: list[str] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        conn.executescript(path.read_text())
        conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, datetime('now'))",
            (path.name,),
        )
        newly.append(path.name)
    conn.commit()
    return newly


def init_db(db_path: Path) -> sqlite3.Connection:
    """Connect and ensure the schema is current."""
    conn = connect(db_path)
    migrate(conn)
    return conn
