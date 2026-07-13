"""Bridge between the backend (auth + runs) and the gateway (chat loop).

The gateway stays ignorant of the backend's internals — it only calls this
object's three methods. Kept here (not in gateway/) so the gateway package has
no import dependency on the backend and can still run standalone.
"""

from __future__ import annotations

from typing import Optional

from security.bearer_auth import extract_bearer

from .db import DB
from .repo import RunRepo, SessionRepo


class GatewayAuth:
    def __init__(self, db: DB) -> None:
        self.sessions = SessionRepo(db)
        self.runs = RunRepo(db)

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
