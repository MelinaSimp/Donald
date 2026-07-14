"""Bridge between the backend (auth + runs) and the gateway (chat loop).

The gateway stays ignorant of the backend's internals — it only calls this
object's three methods. Kept here (not in gateway/) so the gateway package has
no import dependency on the backend and can still run standalone.
"""

from __future__ import annotations

import os
from typing import Optional

from security.bearer_auth import extract_bearer

from .db import DB
from .repo import RunRepo, SessionRepo, UsageRepo


class GatewayAuth:
    def __init__(self, db: DB) -> None:
        self.sessions = SessionRepo(db)
        self.runs = RunRepo(db)
        self.usage = UsageRepo(db)

    def within_budget(self, user_id: str) -> bool:
        """Count this turn against the user's daily cap; False when over.

        Cap comes from DONALD_DAILY_TURN_LIMIT (0 or unset = unlimited). This is
        the guardrail that stops a runaway loop from burning model credits.
        """
        try:
            limit = int(os.getenv("DONALD_DAILY_TURN_LIMIT", "0"))
        except ValueError:
            limit = 0
        allowed, _ = self.usage.check_and_record(user_id, limit)
        return allowed

    def user_for(
        self, authorization: Optional[str] = None, token: Optional[str] = None
    ) -> Optional[str]:
        """Resolve a request to its user_id, from a bearer header or raw token."""
        tok = token or extract_bearer(authorization)
        return self.sessions.resolve(tok) if tok else None

    def start_run(self, user_id: str) -> str:
        return self.runs.start(user_id)

    def finish_run(self, user_id: str, run_id: str, summary: str = "") -> None:
        self.runs.finish(user_id, run_id, summary)
