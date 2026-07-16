"""The tool registry — the thing you extend forever.

Adding a capability = write one self-contained tool and register it. Never edit
the core loop. Each tool carries a clear name, a one-line "when to use it"
description (written for the model, not a compiler), and a typed input schema.

Per-tool safety lives here too: `consequential=True` flags a tool that sends,
spends, deletes, or changes a setting. The agent's confirmation gate (Tier 6)
reads that flag before running the tool — for typed, spoken, and
heartbeat-initiated calls alike.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]
    consequential: bool = False

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """Run the tool, turning any failure into a plain-language error the
        model can reason over rather than a crash (Tier 2)."""
        try:
            return ToolResult(self.handler(tool_input or {}))
        except Exception as e:  # noqa: BLE001 — a tool failing is a feature, not a bug
            return ToolResult(f"Tool '{self.name}' failed: {e}", is_error=True)


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], str],
        consequential: bool = False,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        self._tools[name] = Tool(name, description, input_schema, handler, consequential)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        """The whole registry, handed to the model each turn."""
        return [t.spec() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)


# Tiny helpers shared by tool schemas -------------------------------------------------
def obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def string(desc: str) -> dict[str, Any]:
    return {"type": "string", "description": desc}
