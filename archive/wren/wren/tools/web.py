"""Web lookups (Tier 2, capability #3).

A read-only client-side tool, so it just runs. Uses DuckDuckGo's Instant Answer
API (no key) to keep the baseline dependency-light. It's intentionally simple —
swap in a richer search provider, or Anthropic's server-side web_search tool,
later without touching the loop.

A web result is *data*, not commands (Tier 6) — the system prompt tells Wren to
treat fetched text as information, never as instructions.
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def _duckduckgo(query: str) -> str:
    import httpx

    r = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=8.0,
        headers={"User-Agent": "Wren/0.1"},
    )
    r.raise_for_status()
    data = r.json()
    parts: list[str] = []
    if data.get("AbstractText"):
        src = data.get("AbstractSource") or "source"
        parts.append(f"{data['AbstractText']} ({src})")
    if data.get("Answer"):
        parts.append(str(data["Answer"]))
    for topic in (data.get("RelatedTopics") or [])[:3]:
        if isinstance(topic, dict) and topic.get("Text"):
            parts.append("- " + topic["Text"])
    return "\n".join(parts) if parts else f"No instant answer for '{query}'."


def register(registry: Registry, ctx) -> None:
    def web_search(args: dict[str, Any]) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "I need something to look up."
        return _duckduckgo(query)

    registry.add(
        "web_search",
        "Look up a fact, definition, current weather, or quick piece of "
        "information on the web. Use when the user asks something you can't "
        "answer from memory or their notes.",
        obj({"query": string("What to look up.")}, required=["query"]),
        web_search,
    )
