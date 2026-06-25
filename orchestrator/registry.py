"""The shared tool registry — Tier 2's backbone.

One source of truth for "what a tool is" (name, schema, handler), and many
read-only *views* of "which tools a given agent is allowed to use". Routing
(Tier 1), allowlist filtering (Tier 5), and runtime dispatch registration
(Tier 6) all lean on this single registry rather than re-implementing tools
per agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

# A tool handler takes the validated input dict the model produced and returns
# a string result that gets fed back into the agent loop as a tool_result.
ToolHandler = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    """A single capability the orchestration layer knows how to run.

    `requires_confirmation` is declared here (the cleanest home for it) but is
    *not* acted on yet — the human-in-the-loop gate is Tier 4. It lives on the
    definition now so the registry schema stays stable when that tier lands.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    requires_confirmation: bool = False  # reserved for Tier 4

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Render the wire-format tool definition the Messages API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """The global catalog of tools. Built once, viewed many times."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def view(self, allowed: Iterable[str]) -> "ToolView":
        """Return a least-privilege view exposing exactly `allowed`.

        Unknown names in the allowlist fail loudly here, at agent-construction
        time, rather than silently shrinking an agent's toolbox at runtime.
        """
        allowed = list(allowed)
        missing = [n for n in allowed if n not in self._tools]
        if missing:
            raise KeyError(f"allowlist references unknown tools: {missing}")
        return ToolView(self, allowed)


class ToolView:
    """A filtered, read-only window onto the registry.

    An agent holds a view, never the registry itself, so it can only ever see
    — and reach — the tools its job requires. This is the enforcement point for
    least privilege (Tier 2) and the substrate for allowlists (Tier 5).
    """

    def __init__(self, registry: ToolRegistry, allowed: list[str]) -> None:
        self._registry = registry
        # Sorted for a deterministic tool order — stable prompt prefix, better
        # prompt caching, and reproducible behavior across runs.
        self._allowed = sorted(allowed)

    def names(self) -> list[str]:
        return list(self._allowed)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._registry.get(n).to_anthropic_schema() for n in self._allowed]

    def get(self, name: str) -> Tool:
        """Look up a tool the agent is allowed to use.

        A name outside the allowlist raises PermissionError even if it exists
        in the global registry — a hallucinated tool name can't escape scope.
        """
        if name not in self._allowed:
            raise PermissionError(f"tool {name!r} is not in this agent's allowlist")
        return self._registry.get(name)
