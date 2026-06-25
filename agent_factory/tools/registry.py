"""The global tool registry.

A :class:`Tool` is name + JSON schema + an ``execute`` callable, plus the
crucial ``factory_allowed`` flag. The Factory only ever offers
``factory_allowed`` tools to the agents it spawns — secrets-bearing,
destructive, or payment tools stay ``factory_allowed=False`` and are never
handed out.

The registry is mutable at runtime: the Tier 5 watcher registers and
unregisters ``dispatch_to_<slug>`` tools as agents are approved or archived,
so the host never restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    execute: Callable[[dict[str, Any]], Any]
    # If False, the Factory must never offer this tool to a spawned agent.
    factory_allowed: bool = True


def tool_to_def(tool: Tool) -> dict[str, Any]:
    """Convert a Tool to the Anthropic tool-definition shape."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def tool_result(tool_use_id: str, content: Any, *, is_error: bool = False) -> dict[str, Any]:
    """Build a tool_result content block for the next user turn."""
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content if isinstance(content, str) else str(content),
    }
    if is_error:
        block["is_error"] = True
    return block


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool, *, replace: bool = False) -> None:
        if tool.name in self._tools and not replace:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def list_factory_allowed(self) -> list[Tool]:
        """The catalog the Factory may pick a spawned agent's allowlist from."""
        return [t for t in self._tools.values() if t.factory_allowed]

    def factory_allowed_names(self) -> list[str]:
        return [t.name for t in self.list_factory_allowed()]
