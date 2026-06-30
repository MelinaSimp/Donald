"""Donald — a cocky, comedic personality agent with drift-proof persistence."""

from .conversation import ConversationManager, Message
from .personality import (
    append_voice_cue,
    build_system_prompt,
    load_personality,
)

__all__ = [
    "ConversationManager",
    "Message",
    "append_voice_cue",
    "build_system_prompt",
    "load_personality",
]
