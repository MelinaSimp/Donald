"""Reminders & to-dos (Tier 2, capability #1).

Read/write tools over a plain JSON list. add/list/complete are non-consequential
(creating a to-do is safe). Deleting is routed through delete_data, which IS
gated (Tier 6) — so clearing your list always asks first.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..store import load_json, save_json
from .base import Registry, obj, string


class Reminders:
    """The shared reminders backend — also read by the heartbeat (Tier 5)."""

    def __init__(self, path: Path):
        self.path = path

    def _all(self) -> list[dict[str, Any]]:
        return load_json(self.path, [])

    def _save(self, items: list[dict[str, Any]]) -> None:
        save_json(self.path, items)

    def add(self, text: str, due: str | None = None) -> dict[str, Any]:
        items = self._all()
        item = {
            "id": (max((i["id"] for i in items), default=0) + 1),
            "text": text,
            "due": due,
            "done": False,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        items.append(item)
        self._save(items)
        return item

    def list(self, include_done: bool = False) -> list[dict[str, Any]]:
        return [i for i in self._all() if include_done or not i["done"]]

    def complete(self, reminder_id: int) -> dict[str, Any] | None:
        items = self._all()
        for i in items:
            if i["id"] == reminder_id:
                i["done"] = True
                self._save(items)
                return i
        return None

    def delete(self, reminder_id: int) -> bool:
        items = self._all()
        kept = [i for i in items if i["id"] != reminder_id]
        if len(kept) == len(items):
            return False
        self._save(kept)
        return True


def register(registry: Registry, ctx) -> None:
    reminders: Reminders = ctx.reminders

    def add_reminder(args: dict[str, Any]) -> str:
        text = (args.get("text") or "").strip()
        if not text:
            return "I need the reminder text."
        item = reminders.add(text, args.get("due") or None)
        when = f" (due {item['due']})" if item["due"] else ""
        return f"Added reminder #{item['id']}: {item['text']}{when}"

    def list_reminders(args: dict[str, Any]) -> str:
        items = reminders.list(include_done=bool(args.get("include_done")))
        if not items:
            return "Nothing on your list."
        lines = []
        for i in items:
            mark = "x" if i["done"] else " "
            due = f" — due {i['due']}" if i.get("due") else ""
            lines.append(f"[{mark}] #{i['id']} {i['text']}{due}")
        return "\n".join(lines)

    def complete_reminder(args: dict[str, Any]) -> str:
        rid = args.get("id")
        if rid is None:
            return "I need the reminder id to complete."
        item = reminders.complete(int(rid))
        return f"Marked #{rid} done: {item['text']}" if item else f"No reminder #{rid}."

    registry.add(
        "add_reminder",
        "Add a reminder or to-do for the user. Use this whenever the user asks "
        "to be reminded of something or wants to capture a task.",
        obj(
            {
                "text": string("What to be reminded of."),
                "due": string("Optional ISO datetime (YYYY-MM-DDTHH:MM) it's due."),
            },
            required=["text"],
        ),
        add_reminder,
    )
    registry.add(
        "list_reminders",
        "List the user's open reminders and to-dos. Use when the user asks "
        "what's on their list, what's due, or what they need to do.",
        obj({"include_done": {"type": "boolean", "description": "Include completed items."}}),
        list_reminders,
    )
    registry.add(
        "complete_reminder",
        "Mark a reminder as done by its id. Use when the user says they've "
        "finished or done a task.",
        obj({"id": {"type": "integer", "description": "The reminder id."}}, required=["id"]),
        complete_reminder,
    )
