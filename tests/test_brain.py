"""Tests for Donald's brain — the reason-and-act loop.

A scripted fake Anthropic client stands in for the real API so the full
tool-use cycle (model → Hermes → model → spoken reply) runs offline.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donald.brain import DonaldBrain  # noqa: E402
from donald.hermes import Hermes  # noqa: E402


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(tid, name, inp):
    return SimpleNamespace(type="tool_use", id=tid, name=name, input=inp)


class FakeClient:
    """Replays a queue of scripted responses, one per messages.create call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _brain(responses, **hermes_kwargs):
    return DonaldBrain(
        client=FakeClient(responses),
        hermes=Hermes(dry_run=True, **hermes_kwargs),
        personality_text="PERSONALITY",
    )


def test_plain_reply_no_tools():
    resp = SimpleNamespace(content=[_text("Tremendous question, Champ.")], stop_reason="end_turn")
    brain = _brain([resp])
    result = brain.take_turn("who are you?")
    assert result.reply == "Tremendous question, Champ."
    assert result.actions == []


def test_tool_round_executes_then_replies():
    responses = [
        SimpleNamespace(
            content=[_tool_use("t1", "run_shell", {"command": "date"})],
            stop_reason="tool_use",
        ),
        SimpleNamespace(content=[_text("Done. It's go time.")], stop_reason="end_turn"),
    ]
    brain = _brain(responses)
    result = brain.take_turn("what time is it")
    assert result.reply == "Done. It's go time."
    assert len(result.actions) == 1
    assert result.actions[0]["action"] == "run_shell"
    assert result.actions[0]["ok"]


def test_tools_and_system_passed_to_api():
    resp = SimpleNamespace(content=[_text("hi")], stop_reason="end_turn")
    brain = _brain([resp])
    brain.take_turn("hey")
    call = brain.client.calls[0]
    assert call["tools"], "Hermes tool specs must be sent to the model"
    # System blocks: personality (cached), tonal checkpoint, operator briefing,
    # and — when context sensing succeeds — an ambient-context block.
    assert len(call["system"]) >= 3
    assert any("Hermes" in b["text"] for b in call["system"])


def test_risky_action_surfaces_needs_confirmation():
    responses = [
        SimpleNamespace(
            content=[_tool_use("t1", "run_shell", {"command": "git push --force"})],
            stop_reason="tool_use",
        ),
        SimpleNamespace(
            content=[_text("That'll force-push. Want me to pull the trigger?")],
            stop_reason="end_turn",
        ),
    ]
    brain = _brain(responses)
    result = brain.take_turn("force push my branch")
    assert result.awaiting_confirmation
    assert result.actions[0]["needs_confirmation"]
    assert result.actions[0]["confirm_token"]


def test_voice_cue_not_persisted_in_history():
    resp = SimpleNamespace(content=[_text("hi")], stop_reason="end_turn")
    brain = _brain([resp])
    brain.take_turn("hello there")
    stored = [m for m in brain.conversation.history if m.role == "user"]
    assert stored[0].content == "hello there"  # clean — cue rode the API copy only


def test_tool_round_cap_closes_turn():
    # Every response asks for another tool call — the loop must bail gracefully.
    forever = [
        SimpleNamespace(
            content=[_tool_use(f"t{i}", "run_shell", {"command": "echo loop"})],
            stop_reason="tool_use",
        )
        for i in range(20)
    ]
    brain = _brain(forever)
    result = brain.take_turn("loop forever")
    assert result.reply  # a spoken fallback, not a crash
    assert len(brain.client.calls) <= 8
