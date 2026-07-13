"""End-to-end memory loop through the gateway: what the user says in one turn
is remembered and injected into the system prompt on the next — the thing that
makes Donald feel like it knows you. No LLM: a recording fake orchestrator
captures the memory context it was handed. (Per-user isolation of memory is
proven at the store layer in test_memory_store.py.)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import open_db
from backend.gateway_auth import GatewayAuth
from backend.memory_service import MemoryService
from backend.repo import SessionRepo, UserRepo
from gateway.server import add_gateway_routes


class _Reply:
    def __init__(self, text):
        self.text = text
        self.events = [{"type": "final", "text": text}]


class RecordingOrch:
    """Captures the memory_context handed to it on each turn."""

    voice = None

    def __init__(self):
        self.contexts = []

    async def run(self, session, message):
        self.contexts.append(session.memory_context)
        return _Reply(f"echo: {message}")

    async def run_events(self, session, message):  # pragma: no cover - unused here
        self.contexts.append(session.memory_context)
        for ev in _Reply(f"echo: {message}").events:
            yield ev


class _Settings:
    pass


@pytest.fixture
def rig():
    db = open_db("sqlite://:memory:")
    user = UserRepo(db).create("remember@example.com", "longenough1")
    token = SessionRepo(db).issue(user.id)
    app = FastAPI()
    orch = RecordingOrch()
    add_gateway_routes(
        app, orch, _Settings(), auth=GatewayAuth(db), memory=MemoryService(db)
    )
    return TestClient(app), token, orch


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_says_then_remembers_next_turn(rig):
    client, token, orch = rig

    # Turn 1: tell Donald something durable. No prior memory yet.
    client.post("/api/chat", json={"message": "remember I love sailing"},
                headers=_auth(token))
    assert orch.contexts[0] == ""

    # Turn 2: an unrelated ask — the remembered fact is injected into the prompt.
    client.post("/api/chat", json={"message": "what should we do this weekend?"},
                headers=_auth(token))
    injected = orch.contexts[1]
    assert "sailing" in injected
    assert "user" in injected.lower()  # framed as "what you know about the user"
