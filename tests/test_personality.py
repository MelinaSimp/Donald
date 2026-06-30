"""Structural tests for the personality-persistence layer.

These prove the wiring is correct: the cue lands in the right place, never
pollutes history, skips tool rounds, and carries the voice + guardrail.
Whether Donald is *actually* funny is for a human to judge in a live chat.
"""

from donald.conversation import ConversationManager
from donald.personality import (
    _VOICE_CUE,
    append_voice_cue,
    build_system_prompt,
    load_personality,
)


def test_cue_appears_on_last_user_message():
    conv = ConversationManager()
    conv.add_user_message("how do I reverse a list?")
    messages = conv.messages_for_api()
    append_voice_cue(messages)
    assert _VOICE_CUE in messages[-1]["content"]
    assert messages[-1]["role"] == "user"


def test_cue_not_in_stored_history():
    conv = ConversationManager()
    conv.add_user_message("how do I reverse a list?")
    messages = conv.messages_for_api()
    append_voice_cue(messages)
    # The store's own view must remain clean.
    for m in conv.history:
        assert _VOICE_CUE not in str(m.content)
    # A second fetch must not contain the cue either (no compounding).
    assert _VOICE_CUE not in conv.messages_for_api()[-1]["content"]


def test_cue_skipped_for_block_list_content():
    """Tool-result rounds carry a block-list content; the cue must no-op."""
    conv = ConversationManager()
    conv.add_user_message(
        [{"type": "tool_result", "tool_use_id": "x", "content": "42"}]
    )
    messages = conv.messages_for_api()
    append_voice_cue(messages)
    assert messages[-1]["content"] == [
        {"type": "tool_result", "tool_use_id": "x", "content": "42"}
    ]


def test_cue_skipped_when_assistant_is_last():
    conv = ConversationManager()
    conv.add_user_message("hi")
    conv.add_assistant_message("Tremendous to meet you.")
    messages = conv.messages_for_api()
    append_voice_cue(messages)
    assert _VOICE_CUE not in str(messages[-1]["content"])


def test_cue_has_banned_openers_and_positive_direction():
    # Ban-list present...
    assert "Great question" in _VOICE_CUE
    assert "Based on" in _VOICE_CUE
    # ...and a positive direction to aim at, not just prohibitions.
    assert "tremendous" in _VOICE_CUE.lower()
    assert "believe me" in _VOICE_CUE.lower()


def test_cue_voice_examples_come_from_personality_file():
    personality = load_personality().lower()
    # Signature phrases live in both AGENT.md and the cue.
    for phrase in ["tremendous question", "nobody knows python like me"]:
        assert phrase in personality
        assert phrase in _VOICE_CUE.lower()


def test_cue_preserves_cruelty_guardrail():
    assert "never genuinely cruel" in _VOICE_CUE.lower()


def test_system_prompt_caches_personality_and_floats_checkpoint():
    system = build_system_prompt(load_personality())
    assert len(system) == 2
    cached, dynamic = system
    assert cached["cache_control"] == {"type": "ephemeral"}
    assert "DONALD" in cached["text"]
    # Checkpoint is the dynamic, uncached block.
    assert "cache_control" not in dynamic
    assert "Tonal checkpoint" in dynamic["text"]
