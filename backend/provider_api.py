"""Using connected integrations — the payoff of the M4 broker.

Connecting a provider stores an (encrypted, per-user) token; this module spends
it. ``ProviderAPI.whoami`` calls the provider's identity endpoint with the user's
live token — transparently refreshed by the broker if it expired — so "connect
Google/GitHub/Slack" turns into something the app (and, next, the agent) can act
on. The HTTP client is injectable, so the whole path is testable without a real
provider or real credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .oauth import OAuthBroker


@dataclass(frozen=True)
class _WhoAmI:
    url: str
    parse: Callable[[dict], dict]
    header: Callable[[str], dict] = lambda tok: {"Authorization": f"Bearer {tok}"}


# Per-provider identity endpoints, normalized to {provider, id, name}.
WHOAMI: dict[str, _WhoAmI] = {
    "github": _WhoAmI(
        url="https://api.github.com/user",
        parse=lambda d: {"provider": "github", "id": str(d.get("id", "")),
                         "name": d.get("login") or d.get("name") or ""},
    ),
    "google": _WhoAmI(
        url="https://www.googleapis.com/oauth2/v2/userinfo",
        parse=lambda d: {"provider": "google", "id": d.get("id", ""),
                         "name": d.get("email") or d.get("name") or ""},
    ),
    "slack": _WhoAmI(
        url="https://slack.com/api/auth.test",
        parse=lambda d: {"provider": "slack", "id": d.get("user_id", ""),
                         "name": d.get("user") or ""},
    ),
}


class ProviderError(Exception):
    pass


class ProviderAPI:
    def __init__(self, broker: OAuthBroker, http: Any | None = None) -> None:
        self.broker = broker
        self._http = http

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=30.0)
        return self._http

    def _access(self, user_id: str, provider: str) -> Optional[str]:
        tok = self.broker.valid_token(user_id, provider)  # refreshes if expired
        return tok.get("access_token") if tok else None

    def whoami(self, user_id: str, provider: str) -> Optional[dict]:
        """Identity of the connected account, or None if not connected."""
        cfg = WHOAMI.get(provider)
        if cfg is None:
            raise ProviderError(f"whoami not supported for '{provider}'")
        access = self._access(user_id, provider)
        if not access:
            return None
        resp = self._client().get(cfg.url, headers=cfg.header(access))
        if getattr(resp, "status_code", 200) >= 400:
            raise ProviderError(f"{provider} API returned {resp.status_code}")
        return cfg.parse(resp.json())

    def github_list_repos(self, user_id: str, limit: int = 20) -> list[dict]:
        """The user's most-recently-updated GitHub repos (read-only)."""
        access = self._access(user_id, "github")
        if not access:
            raise ProviderError("github is not connected")
        resp = self._client().get(
            f"https://api.github.com/user/repos?per_page={limit}&sort=updated",
            headers={"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"},
        )
        if getattr(resp, "status_code", 200) >= 400:
            raise ProviderError(f"github API returned {resp.status_code}")
        return [{"full_name": r.get("full_name"), "private": r.get("private"),
                 "url": r.get("html_url")} for r in resp.json()]

    def gmail_search(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        """Search the user's Gmail (read-only); returns message id/snippet."""
        access = self._access(user_id, "google")
        if not access:
            raise ProviderError("google is not connected")
        c = self._client()
        listed = c.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages"
            f"?maxResults={limit}&q={query}",
            headers={"Authorization": f"Bearer {access}"},
        )
        if getattr(listed, "status_code", 200) >= 400:
            raise ProviderError(f"gmail API returned {listed.status_code}")
        out = []
        for m in (listed.json().get("messages") or [])[:limit]:
            msg = c.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}?format=metadata",
                headers={"Authorization": f"Bearer {access}"},
            )
            body = msg.json() if getattr(msg, "status_code", 200) < 400 else {}
            out.append({"id": m["id"], "snippet": body.get("snippet", "")})
        return out

    def create_github_issue(
        self, user_id: str, repo: str, title: str, body: str = "", *, confirm: bool = False
    ) -> dict:
        """Open a GitHub issue — a *consequential* action, so it's gated.

        Agents propose, humans dispose: called with ``confirm=False`` (the
        default) it does nothing but return a preview of exactly what it would
        do. Only ``confirm=True`` actually writes to GitHub. The UI/agent shows
        the preview and requires an explicit yes before re-calling with confirm.
        """
        if not repo or "/" not in repo or not title:
            raise ProviderError("need repo as 'owner/name' and a non-empty title")
        preview = {
            "action": "github.create_issue", "repo": repo,
            "title": title, "body": body,
            "summary": f"Open issue “{title}” in {repo}",
        }
        if not confirm:
            return {"requires_confirmation": True, "preview": preview}

        access = self._access(user_id, "github")
        if not access:
            raise ProviderError("github is not connected")
        resp = self._client().post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={"Authorization": f"Bearer {access}",
                     "Accept": "application/vnd.github+json"},
            json={"title": title, "body": body},
        )
        if getattr(resp, "status_code", 200) >= 400:
            raise ProviderError(f"github API returned {resp.status_code}")
        data = resp.json()
        return {"done": True, "url": data.get("html_url"), "number": data.get("number")}
