"""M7 cost guardrail: per-user daily turn cap at the repo and gateway level."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import open_db
from backend.gateway_auth import GatewayAuth
from backend.repo import SessionRepo, UsageRepo, UserRepo
from gateway.server import add_gateway_routes


def _uid(db, email="u@x.com"):
    return UserRepo(db).create(email, "longenough1").id


# ── repo ──────────────────────────────────────────────────────────────────────
def test_cap_denies_after_limit():
    db = open_db("sqlite://:memory:")
    usage = UsageRepo(db)
    uid = _uid(db)
    assert usage.check_and_record(uid, 2) == (True, 1)
    assert usage.check_and_record(uid, 2) == (True, 2)
    assert usage.check_and_record(uid, 2) == (False, 2)   # over cap, not recorded further
    assert usage.today(uid) == 2


def test_zero_limit_is_unlimited():
    db = open_db("sqlite://:memory:")
    usage = UsageRepo(db)
    uid = _uid(db)
    for _ in range(5):
        allowed, _n = usage.check_and_record(uid, 0)
        assert allowed


def test_cap_is_per_user():
    db = open_db("sqlite://:memory:")
    usage = UsageRepo(db)
    a, b = _uid(db, "a@x.com"), _uid(db, "b@x.com")
    usage.check_and_record(a, 1)
    assert usage.check_and_record(a, 1)[0] is False   # a is capped
    assert usage.check_and_record(b, 1)[0] is True    # b is fresh


# ── gateway enforcement ───────────────────────────────────────────────────────
class _Reply:
    def __init__(self, text): self.text = text; self.events = [{"type": "final", "text": text}]


class _Orch:
    voice = None
    async def run(self, session, message): return _Reply("ok")
    async def run_events(self, session, message):
        yield {"type": "final", "text": "ok"}


class _S: pass


def test_gateway_blocks_over_limit(monkeypatch):
    monkeypatch.setenv("DONALD_DAILY_TURN_LIMIT", "2")
    db = open_db("sqlite://:memory:")
    uid = _uid(db, "cap@x.com")
    token = SessionRepo(db).issue(uid)
    app = FastAPI()
    add_gateway_routes(app, _Orch(), _S(), auth=GatewayAuth(db))
    client = TestClient(app)
    hdr = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/chat", json={"message": "1"}, headers=hdr).json()["text"] == "ok"
    assert client.post("/api/chat", json={"message": "2"}, headers=hdr).json()["text"] == "ok"
    third = client.post("/api/chat", json={"message": "3"}, headers=hdr).json()
    assert "usage limit" in third["text"]
