"""The rails (Tier 6): audit trail, cost tally, kill switch, and gates.

- A visible audit log: every tool run, confirmation, and model turn, one JSON
  line each, so when something surprises you the log says what happened.
- A running model-cost tally, so a runaway loop is obvious immediately.
- A kill switch (config.safety.paused) to pause all proactive behaviour at once
  while you can still talk to Wren.
- The confirmation gates that the agent calls before a consequential tool runs.
  Confirmation is per-action and does not generalize.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .tools.base import Tool


class Audit:
    def __init__(self, path: Path):
        self.path = path
        self.total_cost = 0.0

    def __call__(self, event: str, **fields: Any) -> None:
        if "cost_usd" in fields:
            self.total_cost += float(fields["cost_usd"] or 0.0)
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def cost_line(self) -> str:
        return f"~${self.total_cost:.4f} spent on the model this session"


# --- kill switch -----------------------------------------------------------
def is_paused(config) -> bool:
    return bool(config.get("safety.paused", False))


def set_paused(config, paused: bool) -> None:
    config.set("safety.paused", paused)


# --- gates -----------------------------------------------------------------
def console_gate(tool: Tool, tool_input: dict[str, Any], source: str) -> bool:
    """Interactive confirmation for the terminal. States plainly what's about to
    happen and waits for an explicit yes. Used for typed and (relayed) spoken
    turns."""
    print(f"\n  ⚠  Wren wants to: {tool.name}")
    for k, v in (tool_input or {}).items():
        print(f"       {k}: {v}")
    try:
        answer = input("  Approve this action? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


def make_unattended_gate(audit: Audit, inbox=None):
    """Gate for actions with no human present (e.g. heartbeat-initiated). Never
    blocks waiting on a person it can't reach — it times out to the safe default
    (do nothing) and leaves a note for when you're back (Tier 5)."""

    def gate(tool: Tool, tool_input: dict[str, Any], source: str) -> bool:
        note = f"{tool.name} was proposed by {source} but needs your approval."
        audit("unattended_declined", source=source, tool=tool.name, input=tool_input)
        if inbox is not None:
            inbox.add(note, level="loud", kind="needs_approval")
        return False

    return gate
