"""Application assembly — wire the five parts together.

Used by the CLI and the voice loop. Tests build their own Agent with a fake LLM
instead of calling build_app, so the brain is exercisable without an API key.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent import Agent
from .config import Config
from .heartbeat import Inbox
from .llm import build_llm
from .memory import Memory
from .safety import Audit, console_gate
from .tools import build_context, build_registry


@dataclass
class App:
    config: Config
    memory: Memory
    inbox: Inbox
    audit: Audit
    agent: Agent
    ctx: Any  # ToolContext (reminders/notes live here too)


def build_app(config: Config | None = None, gate=console_gate) -> App:
    config = config or Config.load()
    memory = Memory(config.resolve_path("memory.path", "data/memory.json"))
    inbox = Inbox(config.resolve_path("heartbeat.inbox_path", "data/inbox.json"))
    audit = Audit(config.resolve_path("safety.audit_log", "data/audit.log"))

    ctx = build_context(config, memory)
    registry = build_registry(ctx)
    llm = build_llm(config)

    agent = Agent(
        persona=config.get("assistant.persona", "You are Wren."),
        llm=llm,
        registry=registry,
        memory=memory,
        gate=gate,
        audit=audit,
        confirm_tools=set(config.get("safety.confirm_tools", [])),
        max_tool_rounds=config.get("brain.max_tool_rounds", 8),
    )
    return App(config=config, memory=memory, inbox=inbox, audit=audit, agent=agent, ctx=ctx)
