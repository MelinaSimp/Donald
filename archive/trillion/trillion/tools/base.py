"""Tool interface shared by everything Trillion can call.

A tool exposes an Anthropic tool-use ``definition()`` (name + description +
JSON-Schema for its inputs) and an async ``execute()`` that returns a
JSON-safe result dict.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    @abstractmethod
    def definition(self) -> dict[str, Any]:
        """Return the Anthropic tool schema: ``name``, ``description``, ``input_schema``."""

    @abstractmethod
    async def execute(self, **params: Any) -> dict[str, Any]:
        """Run the tool and return a JSON-safe result dict."""
