"""Donald's living self-knowledge subsystem.

The self-knowledge document at ``context/self/donald.md`` mixes
hand-written narrative with AUTO blocks that are regenerated from the
codebase. This package provides:

- :mod:`.parser`     — read/round-trip/replace AUTO blocks safely
"""

from __future__ import annotations

from .parser import AutoBlock, SelfKnowledgeDoc

__all__ = ["AutoBlock", "SelfKnowledgeDoc"]
