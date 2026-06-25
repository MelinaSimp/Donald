"""Tier 1 — the tool registry assembly.

``register_all`` pulls every tool module's tools into a registry. Add a new
capability by writing a module with a ``register(reg)`` function and listing it
here.
"""

from __future__ import annotations

from .base import Registry, Tool, ToolError, tool  # re-exported for convenience
from . import memory_tools, shell_tools, time_tools, web_tools

__all__ = ["Registry", "Tool", "ToolError", "tool", "register_all"]


def register_all(reg: Registry) -> None:
    time_tools.register(reg)
    web_tools.register(reg)
    shell_tools.register(reg)
    memory_tools.register(reg)
