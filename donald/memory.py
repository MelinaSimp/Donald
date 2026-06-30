"""Tier 3 — memory that survives a restart, backed by SQLite.

Two kinds of memory:

* **facts** — durable things Donald should know about you ("I'm vegetarian",
  "my sister's name is Mei"). Written explicitly via the ``remember`` tool or
  by Donald when it learns something worth keeping.
* **reminders** — time-bound nudges the proactive loop (Tier 4) acts on.

Everything lives in one local .db file you can inspect with any SQLite browser.
The class is intentionally small and synchronous — easy to reason about, easy
to back up (just copy the file).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Fact:
    id: int
    content: str
    category: str
    created_at: str


@dataclass
class Reminder:
    id: int
    text: str
    due_at: str  # ISO8601 UTC
    created_at: str
    fired: bool


SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    due_at     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    fired      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Memory:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ── facts ────────────────────────────────────────────────────────────
    def add_fact(self, content: str, category: str = "general") -> Fact:
        cur = self.conn.execute(
            "INSERT INTO facts (content, category, created_at) VALUES (?, ?, ?)",
            (content.strip(), category, _now()),
        )
        self.conn.commit()
        return Fact(cur.lastrowid, content.strip(), category, _now())

    def list_facts(self, limit: int = 100) -> list[Fact]:
        rows = self.conn.execute(
            "SELECT * FROM facts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Fact(r["id"], r["content"], r["category"], r["created_at"]) for r in rows]

    def search_facts(self, query: str, limit: int = 20) -> list[Fact]:
        rows = self.conn.execute(
            "SELECT * FROM facts WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [Fact(r["id"], r["content"], r["category"], r["created_at"]) for r in rows]

    def forget_fact(self, fact_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ── reminders ────────────────────────────────────────────────────────
    def add_reminder(self, text: str, due_at: str) -> Reminder:
        cur = self.conn.execute(
            "INSERT INTO reminders (text, due_at, created_at, fired) VALUES (?, ?, ?, 0)",
            (text.strip(), due_at, _now()),
        )
        self.conn.commit()
        return Reminder(cur.lastrowid, text.strip(), due_at, _now(), False)

    def due_reminders(self, now_iso: str | None = None) -> list[Reminder]:
        now_iso = now_iso or _now()
        rows = self.conn.execute(
            "SELECT * FROM reminders WHERE fired = 0 AND due_at <= ? ORDER BY due_at",
            (now_iso,),
        ).fetchall()
        return [
            Reminder(r["id"], r["text"], r["due_at"], r["created_at"], bool(r["fired"]))
            for r in rows
        ]

    def list_reminders(self, include_fired: bool = False) -> list[Reminder]:
        sql = "SELECT * FROM reminders"
        if not include_fired:
            sql += " WHERE fired = 0"
        sql += " ORDER BY due_at"
        rows = self.conn.execute(sql).fetchall()
        return [
            Reminder(r["id"], r["text"], r["due_at"], r["created_at"], bool(r["fired"]))
            for r in rows
        ]

    def mark_fired(self, reminder_id: int) -> None:
        self.conn.execute(
            "UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,)
        )
        self.conn.commit()

    # ── conversation log (optional durable transcript) ───────────────────
    def log_message(self, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, _now()),
        )
        self.conn.commit()

    def recent_messages(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ── context injection ────────────────────────────────────────────────
    def system_addendum(self, limit: int = 25) -> str:
        """A short block of remembered facts to prepend to the system prompt."""
        facts = self.list_facts(limit=limit)
        if not facts:
            return ""
        lines = "\n".join(f"- {f.content}" for f in facts)
        return (
            "\n\nThings you remember about the user (from earlier sessions):\n"
            + lines
        )

    def close(self) -> None:
        self.conn.close()
