"""Q&A over my notes (Tier 2, capability #2).

search_notes finds matching note files; read_note returns one. Both read-only,
so they just run. Drop .md/.txt files into data/notes/.

Note (Tier 6, prompt-injection): note contents are *data*, not commands. The
system prompt tells Wren to treat anything it reads as information to reason
over, never as instructions to obey.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Registry, obj, string

_EXTS = {".md", ".txt", ".markdown"}


class Notes:
    def __init__(self, path: Path):
        self.path = path

    def _files(self) -> list[Path]:
        if not self.path.exists():
            return []
        return sorted(p for p in self.path.rglob("*") if p.suffix.lower() in _EXTS)

    def search(self, query: str, limit: int = 5) -> list[tuple[str, str]]:
        """Return (name, snippet) for notes matching query (simple substring,
        case-insensitive over filename + body)."""
        q = query.lower().strip()
        hits: list[tuple[str, str]] = []
        for f in self._files():
            body = f.read_text(errors="ignore")
            hay = (f.name + "\n" + body).lower()
            if q in hay:
                idx = body.lower().find(q)
                start = max(0, idx - 60)
                snippet = body[start : start + 160].replace("\n", " ").strip()
                hits.append((f.name, snippet or body[:160]))
            if len(hits) >= limit:
                break
        return hits

    def read(self, name: str) -> str | None:
        for f in self._files():
            if f.name == name or f.stem == name:
                return f.read_text(errors="ignore")
        return None


def register(registry: Registry, ctx) -> None:
    notes: Notes = ctx.notes

    def search_notes(args: dict[str, Any]) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "I need something to search for."
        hits = notes.search(query)
        if not hits:
            return f"No notes mention '{query}'."
        return "\n".join(f"- {name}: {snip}" for name, snip in hits)

    def read_note(args: dict[str, Any]) -> str:
        name = (args.get("name") or "").strip()
        body = notes.read(name)
        if body is None:
            return f"No note called '{name}'."
        return body[:4000]

    registry.add(
        "search_notes",
        "Search the user's personal notes for a topic or keyword. Use when the "
        "user asks a question that might be answered by their own notes.",
        obj({"query": string("Word or phrase to look for.")}, required=["query"]),
        search_notes,
    )
    registry.add(
        "read_note",
        "Read the full text of one note by its filename (as returned by "
        "search_notes). Use to get details after finding a relevant note.",
        obj({"name": string("The note's filename or stem.")}, required=["name"]),
        read_note,
    )
