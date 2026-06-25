"""Tool registry.

Tools are registered conditionally: a Supabase tool only loads when its
connection string is configured, so a missing ``SUPABASE_<SLUG>_URL`` simply
means that project's tool is absent rather than a crash at startup.
"""

from __future__ import annotations

import logging

from trillion.config import Settings
from trillion.tools.base import Tool

logger = logging.getLogger("trillion.tools.registry")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.definition()["name"]
        if name in self._tools:
            raise ValueError(f"Duplicate tool name: {name!r}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def definitions(self) -> list[dict]:
        return [tool.definition() for tool in self._tools.values()]

    @classmethod
    def from_settings(cls, settings: Settings) -> "ToolRegistry":
        registry = cls()

        if settings.supabase_donald_url:
            from trillion.tools.donald_tool import QueryDonaldTool

            registry.register(QueryDonaldTool(settings.supabase_donald_url))

        logger.info(
            "Registered %d tools: %s",
            len(registry),
            ", ".join(registry.names()) or "(none)",
        )
        return registry
