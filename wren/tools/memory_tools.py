"""Memory tools (Tier 4) — let Wren manage its own long-term memory.

remember / update_memory are non-consequential (recording a preference is safe).
Forgetting a fact deletes data, so it routes through the gated delete_data tool
(Tier 6) — Wren can't quietly erase what it knows about you.
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def register(registry: Registry, ctx) -> None:
    memory = ctx.memory

    def remember(args: dict[str, Any]) -> str:
        text = (args.get("fact") or "").strip()
        if not text:
            return "What should I remember?"
        item = memory.add(text)
        return f"Got it — I'll remember that (#{item['id']})."

    def update_memory(args: dict[str, Any]) -> str:
        fid = args.get("id")
        text = (args.get("fact") or "").strip()
        if fid is None or not text:
            return "I need both the fact id and the new text."
        item = memory.update(int(fid), text)
        return f"Updated memory #{fid}." if item else f"No memory #{fid}."

    registry.add(
        "remember",
        "Durably remember a fact about the user — a preference, identity, or "
        "decision worth recalling in future conversations. Use sparingly, for "
        "things worth keeping, not passing chatter. One plain statement per fact.",
        obj({"fact": string("A single plain statement to remember.")}, required=["fact"]),
        remember,
    )
    registry.add(
        "update_memory",
        "Correct or update a remembered fact by its id when it becomes stale.",
        obj(
            {
                "id": {"type": "integer", "description": "The memory id."},
                "fact": string("The corrected statement."),
            },
            required=["id", "fact"],
        ),
        update_memory,
    )
