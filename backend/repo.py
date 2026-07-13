"""Repositories — the only place SQL touches the backend.

Every method that reads or writes user-owned data takes a ``user_id`` and
filters on it. That is the multi-tenant isolation boundary: there is no repo
call that returns another user's tokens, runs, or sessions.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .crypto import TokenCipher
from .db import DB
from .models import AgentRun, Session, User
from .passwords import hash_password, verify_password

SESSION_TTL_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _uid() -> str:
    return uuid.uuid4().hex


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class EmailTaken(Exception):
    """Signup with an email that already exists."""


# ── users + workspaces ──────────────────────────────────────────────────────
class UserRepo:
    def __init__(self, db: DB) -> None:
        self.db = db

    def _row_to_user(self, r: dict[str, Any]) -> User:
        return User(
            id=r["id"], email=r["email"], display_name=r["display_name"],
            country=r["country"], dob=r["dob"], tos_accepted_at=r["tos_accepted_at"],
            status=r["status"], created_at=r["created_at"],
        )

    def create(
        self, email: str, password: str, *, display_name: str = "",
        country: str | None = None, dob: str | None = None, tos_accepted: bool = False,
    ) -> User:
        email = email.strip().lower()
        if self.by_email(email) is not None:
            raise EmailTaken(email)
        now = _iso(_now())
        uid = _uid()
        self.db.execute(
            "INSERT INTO users (id, email, display_name, password_hash, country, "
            "dob, tos_accepted_at, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)",
            (uid, email, display_name, hash_password(password), country, dob,
             now if tos_accepted else None, now),
        )
        # Every user gets one default workspace.
        self.db.execute(
            "INSERT INTO workspaces (id, owner_id, name, created_at) "
            "VALUES (?, ?, 'Personal', ?)",
            (_uid(), uid, now),
        )
        return self.by_id(uid)  # type: ignore[return-value]

    def by_id(self, user_id: str) -> User | None:
        r = self.db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))
        return self._row_to_user(r) if r else None

    def by_email(self, email: str) -> User | None:
        r = self.db.query_one(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        )
        return self._row_to_user(r) if r else None

    def check_password(self, email: str, password: str) -> User | None:
        r = self.db.query_one(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        )
        if not r or not verify_password(password, r["password_hash"]):
            return None
        return self._row_to_user(r)


# ── auth sessions (opaque bearer tokens) ────────────────────────────────────
class SessionRepo:
    def __init__(self, db: DB) -> None:
        self.db = db

    def issue(self, user_id: str, ttl_days: int = SESSION_TTL_DAYS) -> str:
        """Create a session and return the RAW token (shown once, never stored)."""
        token = secrets.token_urlsafe(32)
        now = _now()
        self.db.execute(
            "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at, "
            "revoked) VALUES (?, ?, ?, ?, ?, 0)",
            (_uid(), user_id, _hash_token(token), _iso(now),
             _iso(now + timedelta(days=ttl_days))),
        )
        return token

    def resolve(self, token: str) -> str | None:
        """Return the owning user_id for a live token, or None."""
        if not token:
            return None
        r = self.db.query_one(
            "SELECT user_id, expires_at, revoked FROM sessions WHERE token_hash = ?",
            (_hash_token(token),),
        )
        if not r or r["revoked"]:
            return None
        if r["expires_at"] <= _iso(_now()):
            return None
        return r["user_id"]

    def revoke(self, token: str) -> bool:
        r = self.db.query_one(
            "SELECT id FROM sessions WHERE token_hash = ?", (_hash_token(token),)
        )
        if not r:
            return False
        self.db.execute("UPDATE sessions SET revoked = 1 WHERE id = ?", (r["id"],))
        return True


# ── per-user integration tokens (encrypted) ─────────────────────────────────
class TokenRepo:
    def __init__(self, db: DB, cipher: TokenCipher) -> None:
        self.db = db
        self.cipher = cipher

    def put(self, user_id: str, provider: str, secret: dict[str, Any]) -> None:
        """Store (or replace) the encrypted secret for one provider."""
        now = _iso(_now())
        ciphertext = self.cipher.encrypt(secret)
        existing = self.db.query_one(
            "SELECT id FROM integration_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        if existing:
            self.db.execute(
                "UPDATE integration_tokens SET ciphertext = ?, updated_at = ? "
                "WHERE id = ?",
                (ciphertext, now, existing["id"]),
            )
        else:
            self.db.execute(
                "INSERT INTO integration_tokens (id, user_id, provider, ciphertext, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (_uid(), user_id, provider, ciphertext, now, now),
            )

    def get(self, user_id: str, provider: str) -> dict[str, Any] | None:
        r = self.db.query_one(
            "SELECT ciphertext FROM integration_tokens WHERE user_id = ? "
            "AND provider = ?",
            (user_id, provider),
        )
        return self.cipher.decrypt(r["ciphertext"]) if r else None

    def providers(self, user_id: str) -> list[str]:
        rows = self.db.query(
            "SELECT provider FROM integration_tokens WHERE user_id = ? "
            "ORDER BY provider",
            (user_id,),
        )
        return [r["provider"] for r in rows]

    def delete(self, user_id: str, provider: str) -> bool:
        existing = self.db.query_one(
            "SELECT id FROM integration_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        if not existing:
            return False
        self.db.execute(
            "DELETE FROM integration_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        return True


# ── agent run history ───────────────────────────────────────────────────────
class RunRepo:
    def __init__(self, db: DB) -> None:
        self.db = db

    def start(self, user_id: str, workspace_id: str | None = None) -> str:
        run_id = _uid()
        self.db.execute(
            "INSERT INTO agent_runs (id, user_id, workspace_id, status, summary, "
            "started_at) VALUES (?, ?, ?, 'running', '', ?)",
            (run_id, user_id, workspace_id, _iso(_now())),
        )
        return run_id

    def finish(self, user_id: str, run_id: str, summary: str = "") -> None:
        # user_id in the WHERE clause: a user can only close their own runs.
        self.db.execute(
            "UPDATE agent_runs SET status = 'done', summary = ?, ended_at = ? "
            "WHERE id = ? AND user_id = ?",
            (summary, _iso(_now()), run_id, user_id),
        )

    def list_for(self, user_id: str, limit: int = 50) -> list[AgentRun]:
        rows = self.db.query(
            "SELECT * FROM agent_runs WHERE user_id = ? ORDER BY started_at DESC "
            "LIMIT ?",
            (user_id, limit),
        )
        return [
            AgentRun(
                id=r["id"], user_id=r["user_id"], workspace_id=r["workspace_id"],
                status=r["status"], summary=r["summary"],
                started_at=r["started_at"], ended_at=r["ended_at"],
            )
            for r in rows
        ]
