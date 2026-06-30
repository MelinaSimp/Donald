"""Tier 1 tool — web search.

Uses Brave Search if you set BRAVE_API_KEY (best quality). Otherwise it falls
back to DuckDuckGo's free Instant Answer API so the tool works with no key at
all — good enough to verify the loop and answer simple factual queries.
"""

from __future__ import annotations

import httpx

from .base import Registry, Tool, ToolError


def register(reg: Registry) -> None:
    reg.register(
        Tool(
            name="web_search",
            description=(
                "Search the web for current information and return the top "
                "results as text. Use for anything you might not know or that "
                "could be out of date."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "count": {
                        "type": "integer",
                        "description": "How many results (default 5).",
                    },
                },
                "required": ["query"],
            },
            func=web_search,
        )
    )


def web_search(query: str, ctx, count: int = 5) -> str:
    key = getattr(ctx.config, "brave_api_key", None) if ctx else None
    if key:
        return _brave(query, key, count)
    return _duckduckgo(query, count)


def _brave(query: str, key: str, count: int) -> str:
    try:
        r = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ToolError(f"Brave search failed: {exc}")

    results = (r.json().get("web", {}) or {}).get("results", [])[:count]
    if not results:
        return f"No results for '{query}'."
    out = [f"Results for '{query}':"]
    for i, res in enumerate(results, 1):
        out.append(f"{i}. {res.get('title','')} — {res.get('url','')}\n   {res.get('description','')}")
    return "\n".join(out)


def _duckduckgo(query: str, count: int) -> str:
    try:
        r = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ToolError(f"Search failed: {exc}")

    data = r.json()
    parts: list[str] = []
    if data.get("AbstractText"):
        parts.append(f"{data['AbstractText']} ({data.get('AbstractURL','')})")
    for topic in data.get("RelatedTopics", [])[:count]:
        if isinstance(topic, dict) and topic.get("Text"):
            parts.append(f"- {topic['Text']} ({topic.get('FirstURL','')})")
    if not parts:
        return (
            f"No instant answer for '{query}'. (Set BRAVE_API_KEY for full web "
            "search results.)"
        )
    return f"Results for '{query}':\n" + "\n".join(parts[:count])
