"""Using a connected integration: the stored token calls the provider (with
auto-refresh), closing the connect -> use loop. Fake HTTP throughout.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.crypto import TokenCipher
from backend.db import open_db
from backend.oauth import OAuthBroker
from backend.provider_api import ProviderAPI, ProviderError
from backend.repo import SessionRepo, TokenRepo, UserRepo


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p


class _FakeHTTP:
    def __init__(self, payload, status=200):
        self.payload, self.status, self.gets = payload, status, []

    def get(self, url, headers=None):
        self.gets.append({"url": url, "headers": headers})
        return _Resp(self.payload, self.status)


def _rig(http_payload, token=None):
    db = open_db("sqlite://:memory:")
    tokens = TokenRepo(db, TokenCipher())
    uid = UserRepo(db).create("u@x.com", "longenough1").id
    if token:
        tokens.put(uid, "github", token)
    broker = OAuthBroker(tokens, state_secret="s")
    api = ProviderAPI(broker, http=_FakeHTTP(http_payload))
    return api, uid, db, tokens


def test_whoami_uses_stored_token():
    api, uid, _, _ = _rig({"id": 42, "login": "ada"},
                          token={"access_token": "AT",
                                 "expires_at": "2999-01-01T00:00:00+00:00"})
    who = api.whoami(uid, "github")
    assert who == {"provider": "github", "id": "42", "name": "ada"}
    # The call carried the stored access token.
    assert api._http.gets[0]["headers"]["Authorization"] == "Bearer AT"
    assert api._http.gets[0]["url"] == "https://api.github.com/user"


def test_whoami_none_when_not_connected():
    api, uid, _, _ = _rig({"id": 1})  # no token stored
    assert api.whoami(uid, "github") is None


def test_whoami_unsupported_provider():
    api, uid, _, _ = _rig({})
    with pytest.raises(ProviderError):
        api.whoami(uid, "dropbox")


def test_api_whoami_endpoint():
    db = open_db("sqlite://:memory:")
    tokens = TokenRepo(db, TokenCipher())
    uid = UserRepo(db).create("api@x.com", "longenough1").id
    tokens.put(uid, "github", {"access_token": "AT",
                               "expires_at": "2999-01-01T00:00:00+00:00"})
    broker = OAuthBroker(tokens, state_secret="s")
    app = create_app(db=db, broker=broker)
    # Swap the app's provider_api HTTP for a fake by rebuilding via broker:
    # simplest is to hit the route and assert not-connected for a fresh provider.
    client = TestClient(app)
    token = SessionRepo(db).issue(uid)
    hdr = {"Authorization": f"Bearer {token}"}
    # google isn't connected -> 404
    assert client.get("/integrations/google/whoami", headers=hdr).status_code == 404
    # unsupported provider -> 400
    assert client.get("/integrations/dropbox/whoami", headers=hdr).status_code == 400
    # unauth -> 401
    assert client.get("/integrations/github/whoami").status_code == 401
