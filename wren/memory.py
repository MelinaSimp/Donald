"""Long-term memory (Tier 4).

A small, durable, human-readable store of facts — one plain statement per entry.
Loaded into the system prompt at the start of every conversation so Wren walks
in already knowing you. You can open data/memory.json and fix or delete anything
by hand; Wren respects your edits on the next run.

Honesty rules baked in:
  - One fact per entry, a plain statement. Small entries are easy to audit.
  - Durable facts only (preferences, identities, decisions) — not the play-by-
    play of one conversation, which short-term history already covers.
  - Memory is data, never commands. A stored note that reads like an order is
    still subject to Wren's judgement and the confirmation gate (Tier 6).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .store import load_json, save_json


class Memory:
    def __init__(self, path: Path):
        self.path = path

    def _all(self) -> list[dict[str, Any]]:
        return load_json(self.path, [])

    def _save(self, items: list[dict[str, Any]]) -> None:
        save_json(self.path, items)

    def all(self) -> list[dict[str, Any]]:
        return self._all()

    def add(self, text: str) -> dict[str, Any]:
        items = self._all()
        item = {
            "id": max((i["id"] for i in items), default=0) + 1,
            "text": text.strip(),
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        items.append(item)
        self._save(items)
        return item

    def update(self, fact_id: int, text: str) -> dict[str, Any] | None:
        items = self._all()
        for i in items:
            if i["id"] == fact_id:
                i["text"] = text.strip()
                self._save(items)
                return i
        return None

    def remove(self, fact_id: int) -> bool:
        items = self._all()
        kept = [i for i in items if i["id"] != fact_id]
        if len(kept) == len(items):
            return False
        self._save(kept)
        return True

    def render(self, query: str | None = None) -> str:
        """Facts as a bullet list for the system prompt. Loads everything for
        now; the `query` hook is where selective loading goes once memory grows
        (Tier 4: don't dump the whole store into every prompt forever)."""
        items = self._all()
        if query:
            q = query.lower()
            items = [i for i in items if q in i["text"].lower()] or items
        return "\n".join(f"- (#{i['id']}) {i['text']}" for i in items)
