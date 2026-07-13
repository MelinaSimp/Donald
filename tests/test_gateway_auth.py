"""Gateway <-> backend integration: authenticated, per-user, recorded chat.

Uses a fake orchestrator (no LLM/Hermes) so we test only the auth + run-recording
wiring that ``add_gateway_routes`` adds.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.crypto import TokenCipher
from backend.db import open_db
from backend.gateway_auth import GatewayAuth
from backend.repo import RunRepo, SessionRepo, UserRepo
from gateway.server import add_gateway_routes


class _Reply:
    def __init__(self, text):
        self.text = text
        self.events = [{"type": "final", "text": text}]


class FakeOrch:
    """Minimal stand-in for DonaldOrchestrator."""

    voice = None

    def __init__(self):
        self.seen = []

    async def run(self, session, message):
        self.seen.append((session.session_id, message))
        return _Reply(f"echo: {message}")

    async def run_events(self, session, message):
        for ev in _Reply(f"echo: {message}").events:
            yield ev


class _Settings:
    pass


@pytest.fixture
def rig():
    db = open_db("sqlite://:memory:")
    users, sessions = UserRepo(db), SessionRepo(db)
    user = users.create("chat@example.com", "longenough1")
    token = sessions.issue(user.id)

    app = FastAPI()
    orch = FakeOrch()
    add_gateway_routes(app, orch, _Settings(), auth=GatewayAuth(db))
    return TestClient(app), token, user.id, RunRepo(db), orch


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_chat_requires_auth(rig):
    client, *_ = rig
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    assert client.post("/api/chat", json={"message": "hi"},
                       headers=_auth("garbage")).status_code == 401


def test_authed_chat_replies_and_records_run(rig):
    client, token, user_id, runs, orch = rig
    r = client.post("/api/chat", json={"message": "hello"}, headers=_auth(token))
    assert r.status_code == 200 and r.json()["text"] == "echo: hello"

    # A run was recorded for this user, finished, summarized from the reply.
    my_runs = runs.list_for(user_id)
    assert len(my_runs) == 1
    assert my_runs[0].status == "done" and "echo: hello" in my_runs[0].summary
    # Session key was namespaced by user_id.
    assert orch.seen[0][0].startswith(user_id + ":")


def test_ws_rejects_without_token(rig):
    client, *_ = rig
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "error"


def test_ws_authed_streams_and_records(rig):
    client, token, user_id, runs, _ = rig
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_json({"type": "chat", "message": "yo"})
        ev = ws.receive_json()
        assert ev["type"] == "final" and ev["text"] == "echo: yo"
    assert len(runs.list_for(user_id)) == 1
