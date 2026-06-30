"""Assembly — wires the tiers into one running Donald.

Kept separate from the CLI so the same assembly can be driven by the text loop,
the voice loop, or the proactive background loop. As later tiers come online
they register here: tools (Tier 1), memory (Tier 3), safety (Tier 5).
"""

from __future__ import annotations

from dataclasses import dataclass

from .agent import Agent
from .brain import Brain, make_brain
from .config import SYSTEM_PROMPT, Config
from .tools.base import Registry


@dataclass
class Donald:
    config: Config
    brain: Brain
    registry: Registry
    agent: Agent


def build(config: Config | None = None) -> Donald:
    config = config or Config.load()
    config.ensure_dirs()

    brain = make_brain(config)
    registry = Registry()

    # ── Tier 3: memory. Built first so tools can record into it. ─────────
    from .memory import Memory

    memory = Memory(config.db_path)

    # Shared context handed to any tool that asks for `ctx`.
    registry.context = ToolContext(config=config, memory=memory)

    # ── Tier 1: register the tool set. ───────────────────────────────────
    from .tools import register_all

    register_all(registry)

    # ── Tier 5: safety gate wraps every mutating tool. ───────────────────
    from .safety import install_safety

    install_safety(registry, config)

    # System prompt gets a little memory context injected at build time.
    system = SYSTEM_PROMPT + memory.system_addendum()

    agent = Agent(brain=brain, registry=registry, system=system)
    return Donald(config=config, brain=brain, registry=registry, agent=agent)


@dataclass
class ToolContext:
    """Whatever tools need access to. Passed in as `ctx`."""

    config: Config
    memory: "object"  # donald.memory.Memory (avoid import cycle in annotation)
