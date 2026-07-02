"""Persistent memory — Donald remembers you across restarts.

Without this, every launch is a blank slate: Donald forgets who you are and what
you just did. Memory fixes that with a small SQLite store (stdlib, no deps, one
file under ``~/.donald``):

  * **turns** — every user/assistant line, so a restart can rehydrate the recent
    conversation and pick up where you left off.
  * **facts** — durable things worth keeping ("I prefer dark mode", "my
    co-founder is Luca"), which the brain injects so Donald actually knows you.

The store is thread-safe (the app server is threaded) and everything is plain
data, so it's testable against an in-memory database.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Tuple

DEFAULT_DB = Path.home() / ".donald" / "donald.db"


class Memory:
    """SQLite-backed conversation log + durable facts."""

    def __init__(self, db_path=DEFAULT_DB) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the threaded server touches this from workers.
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY, ts REAL, role TEXT, content TEXT
                );
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY, ts REAL, text TEXT UNIQUE
                );
                """
            )
            self._db.commit()

    # -- conversation log -------------------------------------------------
    def save_turn(self, role: str, content) -> None:
        """Persist one turn. Non-string content (tool rounds) is skipped."""
        if not isinstance(content, str) or not content.strip():
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO turns(ts, role, content) VALUES(?, ?, ?)",
                (time.time(), role, content),
            )
            self._db.commit()

    def recent_turns(self, limit: int = 20) -> List[Tuple[str, str]]:
        """The last ``limit`` turns, oldest-first, as ``(role, content)``."""
        with self._lock:
            rows = self._db.execute(
                "SELECT role, content FROM (SELECT id, role, content FROM turns "
                "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (limit,),
            ).fetchall()
        return [(r, c) for r, c in rows]

    # -- durable facts ----------------------------------------------------
    def remember(self, text: str) -> bool:
        """Store a durable fact. Returns False if empty or already known."""
        text = (text or "").strip()
        if not text:
            return False
        try:
            with self._lock:
                self._db.execute(
                    "INSERT INTO facts(ts, text) VALUES(?, ?)", (time.time(), text)
                )
                self._db.commit()
            return True
        except sqlite3.IntegrityError:  # duplicate (UNIQUE) — already remembered
            return False

    def facts(self, limit: int = 100) -> List[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT text FROM facts ORDER BY id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()


def format_facts(facts: List[str]) -> str:
    """Render known facts as the system block the brain injects (pure)."""
    lines = ["\n## What you know about the user (memory — use it naturally)"]
    lines += [f"- {f}" for f in facts]
    return "\n".join(lines)
