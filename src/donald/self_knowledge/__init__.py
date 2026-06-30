"""Donald's living self-knowledge subsystem.

The self-knowledge document at ``context/self/donald.md`` mixes
hand-written narrative with AUTO blocks that are regenerated from the
codebase. This package provides:

- :mod:`.parser`     — read/round-trip/replace AUTO blocks safely
"""

from __future__ import annotations

from .checker import DriftFinding, check_drift
from .parser import AutoBlock, SelfKnowledgeDoc
from .render import refresh_file, render_file

__all__ = [
    "AutoBlock",
    "SelfKnowledgeDoc",
    "DriftFinding",
    "check_drift",
    "render_file",
    "refresh_file",
]
