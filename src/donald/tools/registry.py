"""The single source of truth for Donald's callable tools.

Both the runtime (system-prompt assembly, dispatch) and the
self-knowledge generators read from a :class:`ToolRegistry` instance, so
the documentation can never drift from what the agent can actually do.
"""

from __future__ import annotations

from typing import Dict, List

from .base import BaseTool


class ToolRegistry:
    """An ordered, name-indexed collection of :class:`BaseTool` instances."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> BaseTool:
        """Register ``tool`` and return it (so it can be used as decorator-ish)."""
        if not tool.name:
            raise ValueError("tool.name must be a non-empty string")
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> BaseTool:
        return self._tools[name]

    def names(self) -> List[str]:
        return sorted(self._tools)

    def tools(self) -> List[BaseTool]:
        """Return all registered tools, sorted by name for stable output."""
        return [self._tools[name] for name in sorted(self._tools)]

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
