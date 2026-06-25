"""Assembly of the system prompt handed to the LLM on each turn.

:func:`build_system_prompt` is the single place where the final prompt
string is produced. Phase 5 of the self-knowledge work injects the
rendered self-knowledge summary here.
"""

from __future__ import annotations

from typing import Optional

from .tools import ToolRegistry, build_default_registry

SYSTEM_PREAMBLE = (
    "You are Donald, a tool-using conversational AI assistant. "
    "You are helpful, concise, and honest about what you can and cannot do."
)


def build_system_prompt(registry: Optional[ToolRegistry] = None) -> str:
    """Return the full system prompt for a turn.

    Args:
        registry: Tool registry to describe. Defaults to the runtime
            registry from :func:`build_default_registry`.
    """
    registry = registry if registry is not None else build_default_registry()
    lines = [SYSTEM_PREAMBLE, "", "Available tools:"]
    for tool in registry.tools():
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)
