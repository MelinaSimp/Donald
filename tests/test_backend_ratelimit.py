"""Auth rate-limiting: repeated bad logins from one IP get locked out (429)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.crypto import TokenCipher
from backend.db import open_db
from backend.repo import UserRepo
from security.auth_ratelimit import AuthRateLimiter


def _client(max_fails):
    db = open_db("sqlite://:memory:")
    UserRepo(db).create("rl@example.com", "correct-horse")
    limiter = AuthRateLimiter(max_fails=max_fails, window_seconds=300, lockout_seconds=900)
    return TestClient(create_app(db=db, cipher=TokenCipher(), rate_limiter=limiter))


def test_bad_logins_eventually_locked_out():
    client = _client(max_fails=3)
    bad = {"email": "rl@example.com", "password": "wrong"}
    # First 3 wrong attempts: 401 (rejected but allowed to try).
    for _ in range(3):
        assert client.post("/auth/login", json=bad).status_code == 401
    # Now locked: further attempts are 429 regardless of correctness.
    r = client.post("/auth/login", json=bad)
    assert r.status_code == 429 and "Retry-After" in r.headers
    good = {"email": "rl@example.com", "password": "correct-horse"}
    assert client.post("/auth/login", json=good).status_code == 429


def test_successful_login_does_not_count_against_limit():
    client = _client(max_fails=2)
    good = {"email": "rl@example.com", "password": "correct-horse"}
    for _ in range(5):
        assert client.post("/auth/login", json=good).status_code == 200
