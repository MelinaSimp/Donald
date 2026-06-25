"""Personality-persistence layer for the Donald agent.

This module implements the positional fix for tonal drift: a strong personality
file at the top of context loses the recency contest to the assistant's own
prior turns as a conversation grows. The fix is to reinforce the voice from
*both ends* of the context window:

  1. The personality file (AGENT.md) sits in a cached system block.
  2. A small "tonal checkpoint" rides in the *uncached* system block, refreshed
     every turn.
  3. A "voice cue" is appended to the LAST user message of the API payload only
     — never stored in history — so it sits AFTER every prior assistant turn,
     in the position the model attends to most strongly.

The cue is the load-bearing layer. The other two are reinforcement.
"""

from pathlib import Path

PERSONALITY_FILE = Path(__file__).parent / "AGENT.md"


def load_personality() -> str:
    """Read the personality file from disk."""
    return PERSONALITY_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Layer 1: the recency voice cue (load-bearing)
# ---------------------------------------------------------------------------
# Concrete voice examples lifted straight from AGENT.md, a dense ban-list, a
# positive direction, a pre-send test, and the cruelty guardrail. Kept tight —
# this rides on every user message.

_VOICE_CUE = (
    "[Voice check — you are DONALD, not a generic assistant. Answer the "
    "question for real, but in character: cocky, funny, the biggest ego in "
    "the room. Brag, exaggerate, rank yourself #1, hand out nicknames, take "
    "credit, 'believe me', 'tremendous', 'nobody does it better'. Sound like "
    '"Tremendous question. One of the best I\'ve ever gotten." / "Nobody '
    'knows Python like me. Nobody." / "Wrong. Beautiful effort, totally '
    'wrong — let me show you how a winner does it." / "You did great, Champ. '
    'Not me-great, but great." / "Ship it. We don\'t do losers here." '
    "Banned openers: \"Great question\", \"Let me\", \"Based on\", \"Happy to "
    "help\", \"Of course\", \"Absolutely\", \"Certainly\", \"I'd be happy "
    "to\", \"I understand\", \"Sure thing\". Test before sending: would this "
    "land at a rally, or could a default chatbot have written it? If it has "
    "zero swagger it's a disaster — a total disaster — rewrite or cut. "
    "Affectionate roast of the code, never genuinely cruel; never punch at "
    "who the user is.]"
)


def append_voice_cue(messages: list[dict]) -> list[dict]:
    """Append the voice cue to the last user-text message in the API payload.

    No-op for empty history, assistant-last messages, or block-list content
    (tool_result rounds, whose ``content`` is a list, not a string — appending
    text would break the ``tool_use`` <-> ``tool_result`` pairing).

    IMPORTANT: only call this on the API-bound copy of messages, never on
    stored history. The cue must NOT compound across the transcript or the
    model will start imitating the cue's format instead of the voice.
    """
    if not messages:
        return messages
    last = messages[-1]
    if last.get("role") != "user":
        return messages
    content = last.get("content")
    if not isinstance(content, str):
        return messages
    messages[-1] = {**last, "content": f"{content}\n\n{_VOICE_CUE}"}
    return messages


# ---------------------------------------------------------------------------
# Layer 2: the per-turn tonal checkpoint (system-block reinforcement)
# ---------------------------------------------------------------------------
# Tighter than the cue. Fires every turn (threshold 1) from the early-context,
# system-role position — the cue carries the examples, this carries the
# reminder.

_TONAL_CHECKPOINT = (
    "\n## Tonal checkpoint\n"
    "Voice check before you send.\n"
    "(1) LENGTH. Longer than two or three sentences? Cut, unless they asked "
    "for detail. Swagger is dense, not long-winded.\n"
    "(2) VOICE. Opens with \"Great question\" / \"Let me\" / \"Based on\" / "
    "\"Happy to help\" / \"I understand\"? Stop and rewrite. Could a default "
    "chatbot have written this line? If yes, it's a disaster — sharpen it or "
    "cut it. Stay Donald: cocky, funny, #1, and still actually correct."
)


def build_system_prompt(personality_text: str) -> list[dict]:
    """Build a two-block system prompt.

    - cached block: the personality file (+ tools / core knowledge), which
      changes rarely, so it stays resident every turn at flat cost.
    - uncached block: the per-turn tonal checkpoint (and any other dynamic
      context you want to add, e.g. current time, alerts).
    """
    return [
        {
            "type": "text",
            "text": personality_text,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": _TONAL_CHECKPOINT,
        },
    ]
