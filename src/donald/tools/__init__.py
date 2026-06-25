"""Donald's tool layer: the base interface, the registry, and the builtins."""

from __future__ import annotations

from .base import BaseTool
from .builtin import CalculatorTool, ClockTool, EchoTool, SendEmailTool, WebSearchTool
from .registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    """Construct the registry the runtime uses on every turn.

    This is the canonical registration site. The self-knowledge
    capabilities generator imports and iterates the result of this
    function — it never maintains a parallel list.
    """
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(CalculatorTool())
    registry.register(WebSearchTool())
    registry.register(SendEmailTool())
    registry.register(ClockTool())
    return registry


__all__ = [
    "BaseTool",
    "ToolRegistry",
    "EchoTool",
    "CalculatorTool",
    "WebSearchTool",
    "SendEmailTool",
    "ClockTool",
    "build_default_registry",
]
