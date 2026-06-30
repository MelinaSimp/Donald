"""Connector to the local Hermes agent (NousResearch).

Hermes exposes an **OpenAI-compatible** HTTP server when its API server is
enabled. From ``~/.hermes/.env`` on your machine::

    API_SERVER_ENABLED=true
    API_SERVER_HOST=127.0.0.1
    API_SERVER_PORT=8642
    API_SERVER_KEY=change-me-local-dev

That gives us ``POST {base}/v1/chat/completions`` with a
``Authorization: Bearer <API_SERVER_KEY>`` header — the same shape OpenAI
clients speak. We send Donald's delegated task as a single user message and
return Hermes' final text. Hermes runs the task with its full toolset
(terminal, file ops, web search, memory, skills) on your computer.

This connector holds an ``httpx.AsyncClient`` for connection reuse; call
``aclose()`` on shutdown.
"""

from __future__ import annotations

from typing import Optional

from .base import ConnectorError, ConnectorResult


class HermesConnector:
    """OpenAI-compatible client for the local Hermes API server."""

    name = "hermes"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8642",
        api_key: Optional[str] = None,
        model: str = "hermes",
        timeout_s: float = 120.0,
        client: Optional[object] = None,
    ) -> None:
        # base_url normalised without a trailing slash so path joins are clean.
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._client = client  # injectable for tests; lazily created otherwise

    # -- internal -----------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise ConnectorError(
                    "httpx is required for the Hermes connector "
                    "(pip install httpx)"
                ) from exc
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # -- AgentConnector -----------------------------------------------------
    async def health(self) -> bool:
        """True if Hermes' API server answers ``GET /v1/models``."""
        client = self._get_client()
        try:
            resp = await client.get(
                f"{self.base_url}/v1/models", headers=self._headers()
            )
            return resp.status_code < 500
        except Exception:
            return False

    async def execute(
        self, task: str, *, context: Optional[str] = None
    ) -> ConnectorResult:
        """Delegate one task to Hermes and return its final answer."""
        client = self._get_client()
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": task})

        payload = {"model": self.model, "messages": messages, "stream": False}
        try:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
            )
        except Exception as exc:
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error=f"could not reach Hermes at {self.base_url}: {exc}",
            )

        if resp.status_code >= 400:
            body = _safe_text(resp)
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error=f"Hermes returned HTTP {resp.status_code}: {body}",
            )

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return ConnectorResult(
                ok=False,
                text="",
                connector=self.name,
                error=f"unexpected Hermes response shape: {exc}",
            )

        return ConnectorResult(
            ok=True, text=text, connector=self.name, raw=data
        )

    async def aclose(self) -> None:
        if self._client is not None and hasattr(self._client, "aclose"):
            await self._client.aclose()


def _safe_text(resp) -> str:
    try:
        return resp.text[:300]
    except Exception:
        return "<unreadable body>"
