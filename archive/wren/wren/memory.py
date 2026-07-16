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

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .store import load_json, save_json

_WORD = re.compile(r"[a-z0-9]+")


class Memory:
    def __init__(self, path: Path, full_below: int = 9999, max_facts: int = 9999):
        self.path = path
        # When the store has <= full_below facts, load them all (early on,
        # loading everything is fine). Above that, load only the max_facts most
        # relevant to the current turn — the system prompt stays lean as memory
        # grows (Tier 4).
        self.full_below = full_below
        self.max_facts = max_facts

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
        """Facts as a bullet list for the system prompt. Below full_below facts,
        load them all. Above it, load only the max_facts most relevant to the
        current turn (word overlap with `query`), so the prompt stays lean as
        memory grows. If nothing overlaps, fall back to the most recent facts so
        the prompt is never empty (Tier 4)."""
        items = self._all()
        if not items:
            return ""
        if query is None or len(items) <= self.full_below:
            chosen = items
        else:
            qwords = set(_WORD.findall(query.lower()))

            def score(it: dict[str, Any]) -> int:
                return len(qwords & set(_WORD.findall(it["text"].lower())))

            ranked = sorted(items, key=lambda it: (score(it), it["id"]), reverse=True)
            chosen = sorted(ranked[: self.max_facts], key=lambda it: it["id"])
        return "\n".join(f"- (#{i['id']}) {i['text']}" for i in chosen)
