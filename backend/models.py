"""Plain dataclasses mirroring the schema rows the repositories return."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    id: str
    email: str
    display_name: str
    country: str | None
    dob: str | None
    tos_accepted_at: str | None
    status: str
    created_at: str

    def public(self) -> dict:
        """The user shape safe to return over the API (never the hash)."""
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "country": self.country,
            "created_at": self.created_at,
        }


@dataclass
class Session:
    id: str
    user_id: str
    created_at: str
    expires_at: str
    revoked: bool


@dataclass
class AgentRun:
    id: str
    user_id: str
    workspace_id: str | None
    status: str
    summary: str
    started_at: str
    ended_at: str | None
