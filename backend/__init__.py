"""Donald backend (M1) — accounts, auth, encrypted per-user integration tokens,
and agent-run history. Multi-tenant by construction: every data path is scoped
to a user_id. Runs on SQLite for dev/tests, Postgres in prod (DATABASE_URL)."""

from __future__ import annotations

from .crypto import TokenCipher
from .db import DB, open_db
from .repo import EmailTaken, RunRepo, SessionRepo, TokenRepo, UserRepo

__all__ = [
    "DB", "open_db", "TokenCipher",
    "UserRepo", "SessionRepo", "TokenRepo", "RunRepo", "EmailTaken",
]
