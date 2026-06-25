"""Tier 0 — the text conversation loop.

A plain REPL you can debug before any audio exists. Type to Donald, read the
reply. It maintains history, drives the agent loop, and shows tool activity so
you can watch what Donald is doing. Everything later (voice, proactive) reuses
this same agent; this is just the text front door.
"""

from __future__ import annotations

import sys
from typing import Any

from .agent import Agent

BANNER = """\
┌─ Donald ────────────────────────────────────────────┐
│  Text mode. Type to talk. Commands:                  │
│    /history   show the raw message history           │
│    /reset     clear the conversation                 │
│    /tools     list available tools                   │
│    /quit      exit                                   │
└──────────────────────────────────────────────────────┘"""


class Conversation:
    """Holds history and runs turns through the agent."""

    def __init__(self, agent: Agent, greeting: str | None = None):
        self.agent = agent
        self.messages: list[dict[str, Any]] = []
        self.greeting = greeting

    def send(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        return self.agent.respond(self.messages)

    def reset(self) -> None:
        self.messages.clear()


def _print_tool(name: str, args: dict[str, Any], result: str) -> None:
    preview = result if len(result) <= 200 else result[:200] + "…"
    print(f"   \033[2m· {name}({args}) → {preview}\033[0m", file=sys.stderr)


def run_repl(agent: Agent, greeting: str | None = None) -> None:
    """Blocking text REPL. Wire ``agent.on_tool`` to surface tool calls."""
    agent.on_tool = _print_tool
    convo = Conversation(agent, greeting=greeting)

    print(BANNER)
    if convo.greeting:
        print(f"\nDonald: {convo.greeting}")

    while True:
        try:
            user = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDonald: Goodbye.")
            return

        if not user:
            continue
        if user in ("/quit", "/exit"):
            print("Donald: Goodbye.")
            return
        if user == "/reset":
            convo.reset()
            print("Donald: (memory of this chat cleared)")
            continue
        if user == "/history":
            for m in convo.messages:
                print(f"  {m['role']}: {m['content']}")
            continue
        if user == "/tools":
            names = agent.registry.names()
            print("Donald tools:", ", ".join(names) if names else "(none yet)")
            continue

        reply = convo.send(user)
        print(f"\nDonald: {reply}")
