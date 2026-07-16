"""M1 backend: auth, encryption, and — the milestone's exit gate —
multi-tenant isolation. No live DB needed: an in-memory SQLite + ephemeral
cipher exercise the real repositories and the real FastAPI app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.crypto import TokenCipher
from backend.db import open_db
from backend.passwords import hash_password, verify_password
from backend.repo import EmailTaken, TokenRepo, UserRepo


@pytest.fixture
def client():
    # A fresh in-memory DB + throwaway key per test.
    db = open_db("sqlite://:memory:")
    return TestClient(create_app(db=db, cipher=TokenCipher()))


def _signup(client, email, password="hunter2pass"):
    r = client.post("/auth/signup", json={
        "email": email, "password": password, "display_name": email.split("@")[0],
        "accept_tos": True,
    })
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── password hashing ────────────────────────────────────────────────────────
def test_password_roundtrip_and_reject():
    h = hash_password("correct horse battery staple")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)
    # Two hashes of the same password differ (random salt).
    assert h != hash_password("correct horse battery staple")


# ── token encryption ────────────────────────────────────────────────────────
def test_cipher_roundtrip_and_opacity():
    c = TokenCipher()
    ct = c.encrypt({"access_token": "sekret", "refresh_token": "r"})
    assert "sekret" not in ct  # ciphertext does not leak the secret
    assert c.decrypt(ct) == {"access_token": "sekret", "refresh_token": "r"}


def test_cipher_wrong_key_fails():
    ct = TokenCipher().encrypt({"a": 1})
    with pytest.raises(ValueError):
        TokenCipher().decrypt(ct)  # different ephemeral key


# ── auth flow ────────────────────────────────────────────────────────────────
def test_signup_login_me(client):
    token = _signup(client, "ada@example.com")
    me = client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"

    login = client.post("/auth/login", json={
        "email": "ada@example.com", "password": "hunter2pass"})
    assert login.status_code == 200 and login.json()["token"]


def test_signup_requires_tos(client):
    r = client.post("/auth/signup", json={
        "email": "x@example.com", "password": "longenough1", "accept_tos": False})
    assert r.status_code == 400


def test_duplicate_email_rejected(client):
    _signup(client, "dup@example.com")
    r = client.post("/auth/signup", json={
        "email": "dup@example.com", "password": "longenough1", "accept_tos": True})
    assert r.status_code == 409


def test_bad_password_rejected(client):
    _signup(client, "bob@example.com")
    r = client.post("/auth/login", json={
        "email": "bob@example.com", "password": "nope"})
    assert r.status_code == 401


def test_no_token_is_401(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/integrations").status_code == 401
    assert client.get("/auth/me", headers=_auth("garbage")).status_code == 401


def test_logout_revokes(client):
    token = _signup(client, "leaver@example.com")
    assert client.post("/auth/logout", headers=_auth(token)).status_code == 200
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


# ── THE EXIT GATE: two accounts cannot see each other's data ─────────────────
def test_tenant_isolation(client):
    alice = _signup(client, "alice@example.com")
    bob = _signup(client, "bob@example.com")

    # Each connects their own Google token.
    client.put("/integrations/google", headers=_auth(alice),
               json={"secret": {"access_token": "ALICE_GOOGLE"}})
    client.put("/integrations/slack", headers=_auth(bob),
               json={"secret": {"access_token": "BOB_SLACK"}})

    # Alice sees only her provider; Bob only his.
    assert client.get("/integrations", headers=_auth(alice)).json()["providers"] == ["google"]
    assert client.get("/integrations", headers=_auth(bob)).json()["providers"] == ["slack"]

    # Bob deleting "google" 404s — it isn't his to touch.
    assert client.delete("/integrations/google", headers=_auth(bob)).status_code == 404
    # Alice's token still present after Bob's attempt.
    assert client.get("/integrations", headers=_auth(alice)).json()["providers"] == ["google"]


def test_isolation_at_repo_layer():
    """Even below the API, a repo call scoped to one user never returns another's."""
    db = open_db("sqlite://:memory:")
    users = UserRepo(db)
    tokens = TokenRepo(db, TokenCipher())
    a = users.create("a@x.com", "longenough1")
    b = users.create("b@x.com", "longenough1")

    tokens.put(a.id, "github", {"access_token": "A_GH"})
    assert tokens.get(a.id, "github") == {"access_token": "A_GH"}
    # B asking for the same provider gets nothing — tokens are keyed by user.
    assert tokens.get(b.id, "github") is None
    assert tokens.providers(b.id) == []

    with pytest.raises(EmailTaken):
        users.create("a@x.com", "longenough1")
