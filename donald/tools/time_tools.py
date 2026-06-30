"""Tier 1 tools — time, and reminders the proactive loop can act on."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..memory import Memory
from .base import Registry, Tool, ToolError


def register(reg: Registry) -> None:
    reg.register(
        Tool(
            name="get_time",
            description="Get the current date and time. Returns local and UTC.",
            input_schema={"type": "object", "properties": {}},
            func=get_time,
        )
    )
    reg.register(
        Tool(
            name="set_reminder",
            description=(
                "Schedule a reminder. Give either an absolute ISO time in "
                "'due_at' (UTC) or a relative offset in 'in_minutes'. Donald's "
                "background loop will surface it when due."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to remind about."},
                    "in_minutes": {
                        "type": "number",
                        "description": "Minutes from now until the reminder fires.",
                    },
                    "due_at": {
                        "type": "string",
                        "description": "Absolute UTC ISO8601 time, e.g. 2026-06-25T18:30:00Z.",
                    },
                },
                "required": ["text"],
            },
            func=set_reminder,
        )
    )
    reg.register(
        Tool(
            name="list_reminders",
            description="List pending (not-yet-fired) reminders.",
            input_schema={"type": "object", "properties": {}},
            func=list_reminders,
        )
    )


def get_time() -> str:
    now = datetime.now().astimezone()
    utc = datetime.now(timezone.utc)
    return (
        f"Local: {now.strftime('%A, %d %B %Y, %H:%M:%S %Z')}. "
        f"UTC: {utc.strftime('%Y-%m-%dT%H:%M:%SZ')}."
    )


def set_reminder(
    text: str,
    ctx,
    in_minutes: float | None = None,
    due_at: str | None = None,
) -> str:
    memory: Memory = ctx.memory
    if in_minutes is not None:
        due = datetime.now(timezone.utc) + timedelta(minutes=float(in_minutes))
        due_iso = due.isoformat()
    elif due_at:
        due_iso = _normalise_iso(due_at)
    else:
        raise ToolError("Provide either in_minutes or due_at.")

    rem = memory.add_reminder(text, due_iso)
    return f"Reminder #{rem.id} set for {due_iso}: {text}"


def list_reminders(ctx) -> str:
    memory: Memory = ctx.memory
    rems = memory.list_reminders()
    if not rems:
        return "No pending reminders."
    return "\n".join(f"#{r.id} at {r.due_at}: {r.text}" for r in rems)


def _normalise_iso(s: str) -> str:
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ToolError(f"Couldn't parse time '{s}': {exc}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
