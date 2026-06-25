"""The tool registry — how Donald is allowed to *do* things (Tier 1).

A tool is just a Python function plus a JSON-schema describing its arguments.
Register one with the ``@tool`` decorator and it becomes available to the brain
automatically. The registry hands the brain the Anthropic-shaped schemas and
dispatches tool calls back to the functions.

Every tool runs through an optional ``SafetyGate`` (Tier 5). Until that tier is
wired in, the gate is a no-op, so tools work standalone.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[..., Any]
    # If True, this tool changes the world (write/shell/send) and the safety
    # gate should scrutinise it. Read-only tools (time, search) set False.
    mutating: bool = False

    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolError(Exception):
    """Raised by a tool when it fails in an expected way (shown to the brain)."""


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        # Set by Tier 5. Signature: gate(tool, kwargs) -> None | raises/asks.
        self.safety_gate: Callable[[Tool, dict[str, Any]], None] | None = None
        # Optional context object (memory, config, etc.) injected into tools
        # that declare a ``ctx`` parameter.
        self.context: Any = None

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.anthropic_schema() for t in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """Run a tool by name, returning a string result for the brain."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: no such tool '{name}'."

        # Tier 5 hook: may raise (deny) or block on confirmation.
        if self.safety_gate is not None:
            try:
                self.safety_gate(tool, args)
            except ToolError as exc:
                return f"Blocked by safety: {exc}"

        # Inject shared context if the function wants it.
        kwargs = dict(args)
        sig = inspect.signature(tool.func)
        if "ctx" in sig.parameters:
            kwargs["ctx"] = self.context

        try:
            result = tool.func(**kwargs)
        except ToolError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # surface unexpected errors to the brain
            return f"Error running {name}: {exc}"

        if isinstance(result, str):
            return result
        return json.dumps(result, default=str)


# A module-level registry used by the @tool decorator at import time.
default_registry = Registry()


def tool(
    name: str | None = None,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
    mutating: bool = False,
    registry: Registry | None = None,
):
    """Decorator that turns a function into a registered Tool."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        reg = registry or default_registry
        reg.register(
            Tool(
                name=name or func.__name__,
                description=description or (func.__doc__ or "").strip(),
                input_schema=input_schema or {"type": "object", "properties": {}},
                func=func,
                mutating=mutating,
            )
        )
        return func

    return decorator
