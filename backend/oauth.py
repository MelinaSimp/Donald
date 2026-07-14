"""OAuth broker (M4) — one flow that connects any provider for any user.

Every integration reuses this: build an authorize URL, handle the callback,
store the encrypted tokens per user (via TokenRepo), and refresh them when they
expire. Provider client credentials come from the environment; a provider with
no credentials configured is simply "not connectable" until they're set.

    GET /oauth/{provider}/authorize  (bearer)  -> { authorize_url }
    GET /oauth/{provider}/callback?code&state  -> stores tokens, redirects to /app

The ``state`` parameter is HMAC-signed and carries the user_id, so the callback
(which has no bearer header) still knows — and can prove — who it's for. That
also defends against CSRF: a forged or cross-user state fails verification.

Token exchange uses an injectable HTTP client so the whole flow is testable
without a real provider.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

from .repo import TokenRepo


@dataclass(frozen=True)
class Provider:
    name: str
    auth_url: str
    token_url: str
    scopes: tuple[str, ...]
    env_prefix: str
    extra_auth_params: dict[str, str] | None = None


PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        name="google",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=("openid", "email", "https://www.googleapis.com/auth/gmail.readonly"),
        env_prefix="GOOGLE",
        # offline + consent so Google returns a refresh_token.
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    "github": Provider(
        name="github",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scopes=("repo", "read:user"),
        env_prefix="GITHUB",
    ),
    "slack": Provider(
        name="slack",
        auth_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scopes=("chat:write", "channels:read"),
        env_prefix="SLACK",
    ),
}


class OAuthError(Exception):
    pass


def _now() -> float:
    return time.time()


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class OAuthBroker:
    def __init__(
        self,
        tokens: TokenRepo,
        *,
        redirect_base: str | None = None,
        state_secret: str | None = None,
        http: Any | None = None,
        clock=_now,
    ) -> None:
        self.tokens = tokens
        self.redirect_base = (redirect_base or os.getenv("OAUTH_REDIRECT_BASE", "")).rstrip("/")
        self._secret = (
            state_secret or os.getenv("OAUTH_STATE_SECRET")
            or os.getenv("BACKEND_SECRET_KEY") or "dev-insecure-state-secret"
        ).encode()
        self._http = http
        self._clock = clock

    # ── provider config ───────────────────────────────────────────────────
    @staticmethod
    def provider(name: str) -> Provider:
        p = PROVIDERS.get(name)
        if p is None:
            raise OAuthError(f"unknown provider '{name}'")
        return p

    def _creds(self, p: Provider) -> tuple[str, str]:
        cid = os.getenv(f"{p.env_prefix}_CLIENT_ID")
        secret = os.getenv(f"{p.env_prefix}_CLIENT_SECRET")
        if not cid or not secret:
            raise OAuthError(f"{p.name} is not configured (set {p.env_prefix}_CLIENT_ID/_SECRET)")
        return cid, secret

    def is_configured(self, name: str) -> bool:
        try:
            self._creds(self.provider(name))
            return True
        except OAuthError:
            return False

    def _redirect_uri(self, p: Provider) -> str:
        return f"{self.redirect_base}/oauth/{p.name}/callback"

    # ── state (HMAC-signed, carries user_id) ───────────────────────────────
    def _sign_state(self, user_id: str, provider: str) -> str:
        payload = _b64u(json.dumps({
            "u": user_id, "p": provider, "n": secrets.token_urlsafe(8),
            "t": int(self._clock()),
        }).encode())
        mac = _b64u(hmac.new(self._secret, payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{mac}"

    def _verify_state(self, state: str, provider: str, max_age: int = 600) -> str:
        try:
            payload, mac = state.split(".", 1)
        except ValueError:
            raise OAuthError("malformed state")
        expected = _b64u(hmac.new(self._secret, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(mac, expected):
            raise OAuthError("bad state signature")
        data = json.loads(_b64u_decode(payload))
        if data.get("p") != provider:
            raise OAuthError("state provider mismatch")
        if int(self._clock()) - int(data.get("t", 0)) > max_age:
            raise OAuthError("state expired")
        return data["u"]

    # ── flow ───────────────────────────────────────────────────────────────
    def authorize_url(self, user_id: str, provider: str) -> str:
        p = self.provider(provider)
        cid, _ = self._creds(p)
        params = {
            "client_id": cid,
            "redirect_uri": self._redirect_uri(p),
            "response_type": "code",
            "scope": " ".join(p.scopes),
            "state": self._sign_state(user_id, provider),
        }
        if p.extra_auth_params:
            params.update(p.extra_auth_params)
        return f"{p.auth_url}?{urlencode(params)}"

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=30.0)
        return self._http

    def _exchange(self, p: Provider, data: dict[str, str]) -> dict[str, Any]:
        resp = self._client().post(
            p.token_url, data=data, headers={"Accept": "application/json"}
        )
        if getattr(resp, "status_code", 200) >= 400:
            raise OAuthError(f"{p.name} token endpoint returned {resp.status_code}")
        body = resp.json()
        if "error" in body:
            raise OAuthError(f"{p.name}: {body.get('error')}")
        return body

    def _store(self, user_id: str, p: Provider, body: dict[str, Any]) -> None:
        secret: dict[str, Any] = {
            "access_token": body.get("access_token"),
            "token_type": body.get("token_type", "Bearer"),
            "scope": body.get("scope", " ".join(p.scopes)),
        }
        if body.get("refresh_token"):
            secret["refresh_token"] = body["refresh_token"]
        if body.get("expires_in"):
            expires = datetime.now(timezone.utc) + timedelta(seconds=int(body["expires_in"]))
            secret["expires_at"] = expires.isoformat()
        self.tokens.put(user_id, p.name, secret)

    def handle_callback(self, provider: str, code: str, state: str) -> str:
        """Verify state, exchange the code, store tokens. Returns the user_id."""
        p = self.provider(provider)
        cid, csecret = self._creds(p)
        user_id = self._verify_state(state, provider)
        body = self._exchange(p, {
            "client_id": cid, "client_secret": csecret, "code": code,
            "redirect_uri": self._redirect_uri(p), "grant_type": "authorization_code",
        })
        self._store(user_id, p, body)
        return user_id

    def valid_token(self, user_id: str, provider: str) -> Optional[dict[str, Any]]:
        """Return a live access token, refreshing it if expired and possible."""
        p = self.provider(provider)
        tok = self.tokens.get(user_id, provider)
        if not tok:
            return None
        exp = tok.get("expires_at")
        if exp and exp <= datetime.now(timezone.utc).isoformat() and tok.get("refresh_token"):
            cid, csecret = self._creds(p)
            body = self._exchange(p, {
                "client_id": cid, "client_secret": csecret,
                "refresh_token": tok["refresh_token"], "grant_type": "refresh_token",
            })
            # Providers often omit a new refresh_token; keep the old one.
            body.setdefault("refresh_token", tok["refresh_token"])
            self._store(user_id, p, body)
            return self.tokens.get(user_id, provider)
        return tok
