"""The integration toolset Claude (Donald) can call directly.

This is what makes the puzzle full: alongside delegating heavy local work to
Hermes, Donald gets first-class, per-user tools for the accounts the user
connected (M4). Each tool resolves that user's stored, auto-refreshed token and
calls the provider; consequential tools (that write/send) are flagged so the
orchestrator gates them behind a human yes.

Tools are plain data + a handler, so adding one is a dict entry — the schemas
flow to the model and the handlers run server-side with the user's token.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .provider_api import ProviderAPI, ProviderError


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str)[:6000]


def _connected(api: ProviderAPI, uid: str, _inp: dict) -> str:
    provs = api.broker.tokens.providers(uid)
    return _json({"connected": provs or []})


# name, description, input schema, consequential?, handler(provider_api, user_id, input) -> str
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_connected_integrations",
        "description": "List which external accounts (Google, GitHub, Slack) the user has connected and Donald can use.",
        "schema": {"type": "object", "properties": {}},
        "consequential": False,
        "handler": _connected,
    },
    {
        "name": "github_list_repos",
        "description": "List the user's GitHub repositories, most recently updated first. Read-only.",
        "schema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "Max repos (default 20)."}}},
        "consequential": False,
        "handler": lambda api, uid, inp: _json(api.github_list_repos(uid, int(inp.get("limit", 20)))),
    },
    {
        "name": "gmail_search",
        "description": "Search the user's Gmail and return matching message snippets. Read-only. Use Gmail query syntax (e.g. 'from:acme is:unread').",
        "schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "consequential": False,
        "handler": lambda api, uid, inp: _json(api.gmail_search(uid, str(inp.get("query", "")))),
    },
    {
        "name": "github_create_issue",
        "description": "Open a GitHub issue in a repo. CONSEQUENTIAL — this writes to the user's GitHub, so it requires confirmation.",
        "schema": {"type": "object", "properties": {
            "repo": {"type": "string", "description": "owner/name"},
            "title": {"type": "string"},
            "body": {"type": "string"},
        }, "required": ["repo", "title"]},
        "consequential": True,
        "handler": lambda api, uid, inp: _json(
            api.create_github_issue(uid, inp["repo"], inp["title"], inp.get("body", ""), confirm=True)),
    },
]

_BY_NAME = {s["name"]: s for s in TOOL_SPECS}


def anthropic_schemas() -> list[dict]:
    """The tool list to hand the model (Anthropic tool-use shape)."""
    return [{"name": s["name"], "description": s["description"], "input_schema": s["schema"]}
            for s in TOOL_SPECS]


class IntegrationTools:
    """A per-user binding of the toolset to one user's tokens."""

    def __init__(self, provider_api: ProviderAPI, user_id: str) -> None:
        self.api = provider_api
        self.user_id = user_id

    def schemas(self) -> list[dict]:
        return anthropic_schemas()

    def is_tool(self, name: str) -> bool:
        return name in _BY_NAME

    def is_consequential(self, name: str) -> bool:
        spec = _BY_NAME.get(name)
        return bool(spec and spec["consequential"])

    def summarize(self, name: str, inp: dict) -> str:
        """A one-line preview for the confirmation prompt."""
        if name == "github_create_issue":
            return f"Open GitHub issue “{inp.get('title','')}” in {inp.get('repo','')}"
        return f"Run {name}"

    def execute(self, name: str, inp: dict | None) -> str:
        spec = _BY_NAME.get(name)
        if not spec:
            return f"Error: unknown tool '{name}'."
        try:
            return spec["handler"](self.api, self.user_id, inp or {})
        except ProviderError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # never crash the loop
            return f"Error running {name}: {exc}"
