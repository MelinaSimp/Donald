"""Tool registry assembly.

A ToolContext carries the shared services tools need (config + the durable
backends). build_registry wires every tool module in. Adding a capability later
means writing one module with a register(registry, ctx) function and adding one
line here — never touching the agent loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import consequential, memory_tools, notes, reminders, web
from .base import Registry
from .notes import Notes
from .reminders import Reminders


@dataclass
class ToolContext:
    config: Any
    reminders: Reminders
    notes: Notes
    memory: Any  # wren.memory.Memory
    mailer: Any = None  # wren.mailer.Mailer | None (real send behind the gate)


def build_context(config, memory) -> ToolContext:
    from ..mailer import build_mailer

    return ToolContext(
        config=config,
        reminders=Reminders(config.resolve_path("reminders.path", "data/reminders.json")),
        notes=Notes(config.resolve_path("notes.path", "data/notes")),
        memory=memory,
        mailer=build_mailer(config),
    )


def build_registry(ctx: ToolContext) -> Registry:
    registry = Registry()
    # Tier 2 — the safe first capabilities.
    reminders.register(registry, ctx)
    notes.register(registry, ctx)
    web.register(registry, ctx)
    # Tier 4 — memory management.
    memory_tools.register(registry, ctx)
    # Tier 6 — the gated "never without asking" tools (+ safe draft_message).
    consequential.register(registry, ctx)
    return registry
