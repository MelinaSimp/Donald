"""Pure generators that turn code snapshots into AUTO-block markdown.

Each function is pure: given a snapshot (a registry, a list of
integrations, etc.) it returns a markdown string. Gathering the snapshot
from the live registration site is the renderer's job, not the
generator's — which keeps these trivially unit-testable against
fixtures.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from ..integrations import Integration
from ..subagents import SubAgent
from ..tools import ToolRegistry


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    body = ["| " + " | ".join(cells) + " |" for cells in rows]
    if not body:
        return "_none_"
    return "\n".join(lines + body)


def render_capabilities(registry: ToolRegistry) -> str:
    """Render the tool registry as a name/description/category table."""
    rows = [(f"`{t.name}`", t.description, t.category) for t in registry.tools()]
    return _table(("Tool", "Description", "Category"), rows)


def render_integrations(integrations: Sequence[Integration]) -> str:
    """Render external integrations, including configured-or-not status."""
    rows = [
        (
            i.name,
            i.purpose,
            i.category,
            "configured" if i.configured else "not configured",
        )
        for i in integrations
    ]
    return _table(("Integration", "Purpose", "Category", "Status"), rows)


def render_subagents(subagents: Sequence[SubAgent]) -> str:
    """Render specialist sub-agents and their allowed tools."""
    rows = [
        (f"`{s.name}`", s.role, ", ".join(f"`{t}`" for t in s.tools) or "_none_")
        for s in subagents
    ]
    return _table(("Sub-agent", "Role", "Tools"), rows)


def render_recent_activity(commits: Sequence[Tuple[str, str]]) -> str:
    """Render a bulleted list of recent commits (date, subject) pairs."""
    if not commits:
        return "_No commits in the selected window._"
    return "\n".join(f"- `{date}` — {subject}" for date, subject in commits)
