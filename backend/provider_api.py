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

    def whoami(self, user_id: str, provider: str) -> Optional[dict]:
        """Identity of the connected account, or None if not connected."""
        cfg = WHOAMI.get(provider)
        if cfg is None:
            raise ProviderError(f"whoami not supported for '{provider}'")
        tok = self.broker.valid_token(user_id, provider)  # refreshes if expired
        if not tok or not tok.get("access_token"):
            return None
        resp = self._client().get(cfg.url, headers=cfg.header(tok["access_token"]))
        if getattr(resp, "status_code", 200) >= 400:
            raise ProviderError(f"{provider} API returned {resp.status_code}")
        return cfg.parse(resp.json())
