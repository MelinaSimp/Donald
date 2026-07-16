"""Memory panel API: list / add / delete facts, per-user, and the
confirmation-gated GitHub action (agents propose, humans dispose).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.crypto import TokenCipher
from backend.db import open_db
from backend.oauth import OAuthBroker
from backend.provider_api import ProviderAPI, ProviderError
from backend.repo import SessionRepo, TokenRepo, UserRepo


def _client(db=None):
    db = db or open_db("sqlite://:memory:")
    return TestClient(create_app(db=db)), db


def _auth(db, email="mem@x.com"):
    uid = UserRepo(db).create(email, "longenough1").id
    return {"Authorization": f"Bearer {SessionRepo(db).issue(uid)}"}, uid


# ── memory list / add / delete ────────────────────────────────────────────────
def test_memory_add_list_delete():
    client, db = _client()
    hdr, _ = _auth(db)
    assert client.get("/memory", headers=hdr).json()["facts"] == []

    added = client.post("/memory", json={"content": "Prefers concise answers"}, headers=hdr).json()
    assert added["id"]
    facts = client.get("/memory", headers=hdr).json()["facts"]
    assert len(facts) == 1 and facts[0]["content"] == "Prefers concise answers"

    assert client.delete(f"/memory/{added['id']}", headers=hdr).status_code == 200
    assert client.get("/memory", headers=hdr).json()["facts"] == []


def test_memory_is_per_user_and_delete_scoped():
    client, db = _client()
    a_hdr, _ = _auth(db, "a@x.com")
    b_hdr, _ = _auth(db, "b@x.com")
    fid = client.post("/memory", json={"content": "Alice's secret"}, headers=a_hdr).json()["id"]
    # B sees nothing and cannot delete A's fact even with its id.
    assert client.get("/memory", headers=b_hdr).json()["facts"] == []
    assert client.delete(f"/memory/{fid}", headers=b_hdr).status_code == 404
    # A still has it.
    assert len(client.get("/memory", headers=a_hdr).json()["facts"]) == 1


def test_memory_requires_auth():
    client, _ = _client()
    assert client.get("/memory").status_code == 401


# ── confirmation-gated action ─────────────────────────────────────────────────
def test_github_issue_previews_without_confirm():
    client, db = _client()
    hdr, _ = _auth(db)
    r = client.post("/integrations/github/issue",
                    json={"repo": "acme/app", "title": "Bug: crash on save"}, headers=hdr)
    data = r.json()
    assert data["requires_confirmation"] is True
    assert data["preview"]["repo"] == "acme/app"
    assert "Bug: crash on save" in data["preview"]["summary"]


def test_github_issue_confirm_needs_connection():
    # Confirming without a connected GitHub -> a clear 400, not a silent no-op.
    client, db = _client()
    hdr, _ = _auth(db)
    r = client.post("/integrations/github/issue",
                    json={"repo": "acme/app", "title": "x", "confirm": True}, headers=hdr)
    assert r.status_code == 400 and "not connected" in r.json()["detail"]


def test_github_issue_confirm_executes_with_token():
    # With a token + fake HTTP, confirm actually posts to GitHub.
    class _Resp:
        status_code = 201
        def json(self): return {"html_url": "https://github.com/acme/app/issues/7", "number": 7}
    class _HTTP:
        def __init__(self): self.posts = []
        def post(self, url, headers=None, json=None): self.posts.append({"url": url, "json": json}); return _Resp()
        def get(self, *a, **k): return _Resp()

    db = open_db("sqlite://:memory:")
    tokens = TokenRepo(db, TokenCipher())
    uid = UserRepo(db).create("gh@x.com", "longenough1").id
    tokens.put(uid, "github", {"access_token": "AT", "expires_at": "2999-01-01T00:00:00+00:00"})
    http = _HTTP()
    api = ProviderAPI(OAuthBroker(tokens, state_secret="s"), http=http)

    preview = api.create_github_issue(uid, "acme/app", "Ship it")
    assert preview["requires_confirmation"]
    done = api.create_github_issue(uid, "acme/app", "Ship it", "body", confirm=True)
    assert done["done"] and done["number"] == 7
    assert http.posts[0]["url"].endswith("/repos/acme/app/issues")
    assert http.posts[0]["json"]["title"] == "Ship it"
