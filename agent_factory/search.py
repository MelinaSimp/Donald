"""Pluggable web-search backend.

Real web search needs an external provider (Tavily, Serper, Brave, Bing, or
Anthropic's native ``web_search_20250305`` server tool). Rather than hard-wire
one, the Factory depends on this small interface so the whole system runs and
is testable offline.

* :class:`NullSearchBackend` — the default; returns nothing and tells the
  model search is unavailable. The research loop still completes (the model
  emits a best-effort report on the final forced turn).
* :class:`StaticSearchBackend` — canned results, used in tests.

To wire real search, implement :class:`SearchBackend.search` against your
provider and pass it to ``build_default_registry`` and the research runner.
"""

from __future__ import annotations

from typing import Protocol


class SearchResult(dict):
    """A search hit: keys ``url``, ``title``, ``content``."""


class SearchBackend(Protocol):
    def search(self, query: str) -> list[dict]:
        """Return a list of {url, title, content} dicts for *query*."""
        ...


class NullSearchBackend:
    """No external provider configured."""

    def search(self, query: str) -> list[dict]:  # noqa: D401
        return [
            {
                "url": "",
                "title": "search unavailable",
                "content": (
                    "No web-search backend is configured. Proceed using your "
                    "own knowledge and clearly note sources are unavailable."
                ),
            }
        ]


class StaticSearchBackend:
    """Deterministic backend for tests and offline demos."""

    def __init__(self, results: dict[str, list[dict]] | None = None,
                 default: list[dict] | None = None) -> None:
        self._results = results or {}
        self._default = default or []
        self.queries: list[str] = []

    def search(self, query: str) -> list[dict]:
        self.queries.append(query)
        for key, hits in self._results.items():
            if key.lower() in query.lower():
                return hits
        return self._default
