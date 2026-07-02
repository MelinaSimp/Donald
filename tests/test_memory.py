"""Tests for persistent memory — remembers you across restarts.

Uses a temp DB file so the 'restart' (a second Memory on the same path) is real.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donald.brain import DonaldBrain  # noqa: E402
from donald.hermes import Hermes  # noqa: E402
from donald.memory import Memory, format_facts  # noqa: E402


def test_turns_persist_across_restart(tmp_path):
    db = tmp_path / "m.db"
    m = Memory(db)
    m.save_turn("user", "hello")
    m.save_turn("assistant", "Tremendous.")
    m.close()

    m2 = Memory(db)  # simulate a restart on the same file
    assert m2.recent_turns() == [("user", "hello"), ("assistant", "Tremendous.")]


def test_non_string_turns_are_skipped():
    m = Memory(":memory:")
    m.save_turn("user", [{"type": "tool_result"}])  # tool round, not a spoken line
    m.save_turn("user", "   ")
    assert m.recent_turns() == []


def test_facts_are_unique_and_ordered():
    m = Memory(":memory:")
    assert m.remember("prefers dark mode") is True
    assert m.remember("prefers dark mode") is False  # duplicate
    assert m.remember("co-founder is Luca") is True
    assert m.facts() == ["prefers dark mode", "co-founder is Luca"]
    assert "dark mode" in format_facts(m.facts())


def test_remember_tool_through_hermes():
    m = Memory(":memory:")
    h = Hermes(dry_run=True, memory=m)
    r = h.remember("ships on Fridays")
    assert r.ok and m.facts() == ["ships on Fridays"]
    assert not Hermes(dry_run=True).remember("x").ok  # no memory wired


def _fake_client(reply="ok"):
    resp = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=reply)], stop_reason="end_turn"
    )

    class C:
        def __init__(self):
            self.calls = []
            self.messages = SimpleNamespace(create=self._c)

        def _c(self, **k):
            self.calls.append(k)
            return resp

    return C()


def test_brain_rehydrates_and_injects_facts(tmp_path):
    db = tmp_path / "m.db"
    seed = Memory(db)
    seed.save_turn("user", "call me Champ")
    seed.save_turn("assistant", "You got it, Champ.")
    seed.remember("user is building Donald")
    seed.close()

    brain = DonaldBrain(
        client=_fake_client(), hermes=Hermes(dry_run=True), personality_text="P", memory=Memory(db)
    )
    # Prior conversation was reloaded.
    roles = [m.role for m in brain.conversation.history]
    assert roles == ["user", "assistant"]

    brain.take_turn("what am I building?")
    system = brain.client.calls[0]["system"]
    assert any("building Donald" in b["text"] for b in system)  # facts injected


def test_brain_persists_each_turn(tmp_path):
    db = tmp_path / "m.db"
    m = Memory(db)
    brain = DonaldBrain(
        client=_fake_client("Big answer."), hermes=Hermes(dry_run=True), personality_text="P", memory=m
    )
    brain.take_turn("hey Donald")
    assert m.recent_turns() == [("user", "hey Donald"), ("assistant", "Big answer.")]
