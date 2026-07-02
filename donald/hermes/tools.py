"""The bridge between Donald's brain and Hermes's hands.

Donald reasons with the Anthropic Messages API. To *do* things he calls tools;
this module is the tool layer:

  * :data:`TOOL_SPECS` — the JSON schemas handed to the model (``tools=`` in the
    API call) describing each Hermes capability.
  * :func:`dispatch` — takes a ``tool_use`` block name + input and runs the
    matching :class:`~donald.hermes.engine.Hermes` method, returning an
    :class:`~donald.hermes.engine.ActionResult`.

Keeping the schema and the dispatch table side by side means a new capability
is added in one place: append a spec and a branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .engine import ActionResult, Hermes


TOOL_SPECS = [
    {
        "name": "run_shell",
        "description": (
            "Run a shell command on the user's computer and return its output. "
            "Use for file operations, git, launching scripts, querying the "
            "system — anything a terminal can do. Destructive or risky commands "
            "are gated: you'll get back needs_confirmation, and you must ask the "
            "user out loud before they run. Prefer the most specific, smallest "
            "command that does the job."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command to execute.",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "open_app",
        "description": "Launch a desktop application by its name (e.g. 'Safari', 'Spotify', 'Terminal').",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The application name."}
            },
            "required": ["name"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a URL in the user's default web browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to open."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "set_reminder",
        "description": (
            "Remind the user out loud after a delay. Use when they say 'remind me "
            "in N minutes/seconds to X'. Donald will speak up on his own when it's "
            "due — the user doesn't have to ask again."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "description": "How many seconds from now to remind (e.g. 600 for 10 minutes).",
                },
                "message": {"type": "string", "description": "What to remind them about."},
            },
            "required": ["seconds", "message"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Store a durable fact about the user so you know it in future sessions "
            "(e.g. 'prefers dark mode', 'co-founder is Luca', 'ships on Fridays'). "
            "Use when they tell you something worth keeping, or say 'remember that…'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact to remember, one sentence."}
            },
            "required": ["fact"],
        },
    },
    {
        "name": "confirm_action",
        "description": (
            "Run a previously gated, risky action that the user has now approved "
            "out loud. Pass the confirm_token you received in the earlier "
            "needs_confirmation result. ONLY call this after the user clearly "
            "says yes — never assume approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "confirm_token": {
                    "type": "string",
                    "description": "The token from the needs_confirmation result.",
                }
            },
            "required": ["confirm_token"],
        },
    },
]

# Tool names that, once the user approves, re-run with confirmed=True.
GATED_TOOLS = frozenset({"run_shell", "open_app"})


def dispatch(hermes: "Hermes", name: str, tool_input: dict, confirmed: bool = False) -> "ActionResult":
    """Route one tool call to the matching Hermes method."""
    from .engine import ActionResult

    tool_input = tool_input or {}
    if name == "run_shell":
        return hermes.run_shell(tool_input.get("command", ""), confirmed=confirmed)
    if name == "open_app":
        return hermes.open_app(tool_input.get("name", ""), confirmed=confirmed)
    if name == "open_url":
        return hermes.open_url(tool_input.get("url", ""))
    if name == "set_reminder":
        return hermes.set_reminder(tool_input.get("seconds", 0), tool_input.get("message", ""))
    if name == "remember":
        return hermes.remember(tool_input.get("fact", ""))
    if name == "confirm_action":
        return hermes.confirm(tool_input.get("confirm_token", ""))
    return ActionResult(False, name, f"Hermes has no tool called {name!r}.")
