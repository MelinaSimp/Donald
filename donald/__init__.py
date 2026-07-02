"""Donald — a cocky, comedic voice desktop assistant.

Donald is the voice and the brain; **Hermes** is the hands on the computer.
You say "Donald", a UI wakes, you talk, and Hermes carries out what you ask.

  * :mod:`donald.personality` — the drift-proof personality-persistence layers.
  * :mod:`donald.brain` — the reason-and-act loop (Claude + Hermes tools).
  * :mod:`donald.hermes` — the computer-control execution engine.
  * :mod:`donald.app` — the local voice app server (``python -m donald.app``).
"""

from .brain import DonaldBrain, TurnResult
from .context import format_context, gather_context
from .conversation import ConversationManager, Message
from .hermes import ActionResult, Hermes, detect_platform
from .killswitch import KillSwitch
from .memory import Memory
from .personality import (
    append_voice_cue,
    build_system_prompt,
    load_personality,
)
from .proactive import ProactiveEngine

__all__ = [
    "ConversationManager",
    "Message",
    "DonaldBrain",
    "TurnResult",
    "Hermes",
    "ActionResult",
    "detect_platform",
    "KillSwitch",
    "Memory",
    "ProactiveEngine",
    "gather_context",
    "format_context",
    "append_voice_cue",
    "build_system_prompt",
    "load_personality",
]
