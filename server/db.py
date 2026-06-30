import sqlite3
import json
from datetime import datetime
from typing import Any
from server.config import settings


def get_db() -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database schema."""
    conn = get_db()
    cursor = conn.cursor()

    # Conversation sessions
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """
    )

    # Conversation messages and turns
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """
    )

    # TTS cache: turn_id -> (text, expires_at)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tts_cache (
            turn_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """
    )

    conn.commit()
    conn.close()


def create_session() -> str:
    """Create a new conversation session. Returns session_id."""
    import uuid

    session_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
        (session_id, now, now),
    )
    conn.commit()
    conn.close()

    return session_id


def save_turn(
    session_id: str, role: str, text: str
) -> str:
    """Save a turn (message). Returns turn_id."""
    import uuid

    turn_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO turns (id, session_id, role, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (turn_id, session_id, role, text, now),
    )

    cursor.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
    )
    conn.commit()
    conn.close()

    return turn_id


def get_session_turns(session_id: str) -> list[dict[str, Any]]:
    """Fetch all turns for a session (for LLM context)."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT role, text FROM turns WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def cache_tts_text(turn_id: str, text: str, ttl_seconds: int) -> None:
    """Cache TTS response text with a TTL."""
    from datetime import timedelta

    conn = get_db()
    cursor = conn.cursor()

    now = datetime.utcnow()
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

    cursor.execute(
        "INSERT OR REPLACE INTO tts_cache (turn_id, text, expires_at) VALUES (?, ?, ?)",
        (turn_id, text, expires_at),
    )
    conn.commit()
    conn.close()


def get_cached_tts_text(turn_id: str) -> str | None:
    """
    Fetch cached TTS text if it exists and hasn't expired.
    Does NOT delete on read (non-evicting).
    """
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()
    cursor.execute(
        "SELECT text FROM tts_cache WHERE turn_id = ? AND expires_at > ?",
        (turn_id, now),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0]
    return None


def prune_expired_tts_cache() -> None:
    """Remove expired entries from TTS cache (lazy pruning on write)."""
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()
    cursor.execute("DELETE FROM tts_cache WHERE expires_at <= ?", (now,))
    conn.commit()
    conn.close()
