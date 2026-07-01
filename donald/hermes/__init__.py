"""Hermes — the computer-control engine behind Donald.

Donald talks; Hermes acts. Import the engine and tool layer from here::

    from donald.hermes import Hermes, dispatch, TOOL_SPECS
"""

from .computer import ComputerController, ComputerResult, computer_tool_spec
from .engine import ActionResult, Hermes, detect_platform
from .tools import GATED_TOOLS, TOOL_SPECS, dispatch

__all__ = [
    "ActionResult",
    "Hermes",
    "detect_platform",
    "GATED_TOOLS",
    "TOOL_SPECS",
    "dispatch",
    "ComputerController",
    "ComputerResult",
    "computer_tool_spec",
]
