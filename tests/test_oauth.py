"""M4 OAuth broker: authorize URL, signed state (CSRF/cross-user defense),
code->token exchange with encrypted storage, and refresh. Fake HTTP throughout.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.crypto import TokenCipher
from backend.db import open_db
from backend.oauth import OAuthBroker, OAuthError
from backend.repo import SessionRepo, TokenRepo, UserRepo


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


class _FakeHTTP:
    """Records token-endpoint posts; returns a scripted body."""

    def __init__(self, body):
        self.body = body
        self.posts = []

    def post(self, url, data=None, headers=None):
        self.posts.append({"url": url, "data": data})
        return _Resp(self.body)


CREDS = {
    "GOOGLE_CLIENT_ID": "gid", "GOOGLE_CLIENT_SECRET": "gsecret",
    "OAUTH_REDIRECT_BASE": "https://app.example.com",
}


def _broker(http=None, **secret):
    db = open_db("sqlite://:memory:")
    tokens = TokenRepo(db, TokenCipher())
    broker = OAuthBroker(tokens, http=http, redirect_base="https://app.example.com",
                         state_secret="test-secret")
    return broker, tokens, db


def _mk_user(db, email="u@x.com"):
    return UserRepo(db).create(email, "longenough1").id


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k, v in CREDS.items():
        monkeypatch.setenv(k, v)


# ── authorize URL + state ────────────────────────────────────────────────────
def test_authorize_url_has_expected_params():
    broker, _, _ = _broker()
    url = broker.authorize_url("user-1", "google")
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["gid"]
    assert q["redirect_uri"] == ["https://app.example.com/oauth/google/callback"]
    assert q["response_type"] == ["code"]
    assert "gmail.readonly" in q["scope"][0]
    assert q["access_type"] == ["offline"]  # so Google returns a refresh_token
    # state round-trips to the user.
    assert broker._verify_state(q["state"][0], "google") == "user-1"


def test_state_rejects_tampering_and_cross_provider():
    broker, _, _ = _broker()
    state = broker.authorize_url("user-1", "google").split("state=")[1].split("&")[0]
    with pytest.raises(OAuthError):
        broker._verify_state(state + "x", "google")          # tampered
    with pytest.raises(OAuthError):
        broker._verify_state(state, "github")                # wrong provider
    # A different broker (different secret) can't forge acceptance.
    other = OAuthBroker(broker.tokens, state_secret="other-secret")
    with pytest.raises(OAuthError):
        other._verify_state(state, "google")


def test_authorize_unconfigured_provider_errors(monkeypatch):
    broker, _, _ = _broker()
    with pytest.raises(OAuthError):
        broker.authorize_url("user-1", "github")  # no GITHUB_CLIENT_ID set


# ── callback exchange + storage ──────────────────────────────────────────────
def test_callback_exchanges_code_and_stores_encrypted():
    http = _FakeHTTP({"access_token": "AT", "refresh_token": "RT",
                      "token_type": "Bearer", "expires_in": 3600})
    broker, tokens, db = _broker(http=http)
    uid0 = _mk_user(db, "cb@x.com")
    state = broker._sign_state(uid0, "google")

    uid = broker.handle_callback("google", code="abc", state=state)
    assert uid == uid0
    # Exchange used the auth-code grant with our code.
    assert http.posts[0]["data"]["grant_type"] == "authorization_code"
    assert http.posts[0]["data"]["code"] == "abc"
    # Stored, decrypted, scoped to the user.
    stored = tokens.get(uid0, "google")
    assert stored["access_token"] == "AT" and stored["refresh_token"] == "RT"
    assert "expires_at" in stored


def test_callback_rejects_forged_state():
    broker, _, _ = _broker(http=_FakeHTTP({"access_token": "x"}))
    with pytest.raises(OAuthError):
        broker.handle_callback("google", code="abc", state="forged.sig")


# ── refresh ──────────────────────────────────────────────────────────────────
def test_valid_token_refreshes_when_expired():
    http = _FakeHTTP({"access_token": "NEW", "expires_in": 3600})
    broker, tokens, db = _broker(http=http)
    uid = _mk_user(db, "rf@x.com")
    # Seed an already-expired token with a refresh_token.
    tokens.put(uid, "google", {
        "access_token": "OLD", "refresh_token": "RT",
        "expires_at": "2000-01-01T00:00:00+00:00",
    })
    tok = broker.valid_token(uid, "google")
    assert tok["access_token"] == "NEW"                 # refreshed
    assert tok["refresh_token"] == "RT"                 # preserved
    assert http.posts[-1]["data"]["grant_type"] == "refresh_token"


def test_valid_token_no_refresh_when_live():
    http = _FakeHTTP({"access_token": "SHOULD_NOT_BE_USED"})
    broker, tokens, db = _broker(http=http)
    uid = _mk_user(db, "lv@x.com")
    tokens.put(uid, "google", {"access_token": "LIVE",
                               "expires_at": "2999-01-01T00:00:00+00:00"})
    assert broker.valid_token(uid, "google")["access_token"] == "LIVE"
    assert http.posts == []  # no refresh call


# ── API wiring ───────────────────────────────────────────────────────────────
def test_api_authorize_and_providers():
    db = open_db("sqlite://:memory:")
    http = _FakeHTTP({"access_token": "AT", "expires_in": 3600})
    broker = OAuthBroker(TokenRepo(db, TokenCipher()), http=http,
                         redirect_base="https://app.example.com",
                         state_secret="test-secret")
    client = TestClient(create_app(db=db, broker=broker), follow_redirects=False)
    token = SessionRepo(db).issue(UserRepo(db).create("o@x.com", "longenough1").id)
    hdr = {"Authorization": f"Bearer {token}"}

    provs = client.get("/oauth/providers", headers=hdr).json()["providers"]
    google = next(p for p in provs if p["name"] == "google")
    assert google["configured"] and not google["connected"]

    r = client.get("/oauth/google/authorize", headers=hdr)
    assert r.status_code == 200 and "accounts.google.com" in r.json()["authorize_url"]

    # GitHub isn't configured -> 400.
    assert client.get("/oauth/github/authorize", headers=hdr).status_code == 400

    # Drive the callback with a valid state -> stores token, redirects to /app.
    state = broker._sign_state(
        broker._verify_state(
            r.json()["authorize_url"].split("state=")[1].split("&")[0], "google"),
        "google")
    cb = client.get(f"/oauth/google/callback?code=abc&state={state}")
    assert cb.status_code == 303 and cb.headers["location"].startswith("/app/")
    # Now shows connected.
    provs = client.get("/oauth/providers", headers=hdr).json()["providers"]
    assert next(p for p in provs if p["name"] == "google")["connected"]
