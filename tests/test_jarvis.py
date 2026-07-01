"""Tests for the Jarvis increment: kill switch, context sensing, proactivity.

All offline: no threads left running, no clock dependence (times are injected),
no mic, no API.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime  # noqa: E402

from donald.brain import DonaldBrain  # noqa: E402
from donald.context import format_context, gather_context  # noqa: E402
from donald.hermes import Hermes  # noqa: E402
from donald.killswitch import KillSwitch  # noqa: E402
from donald.proactive import ProactiveEngine  # noqa: E402


# -- kill switch -------------------------------------------------------------

def test_kill_switch_engages_and_releases():
    ks = KillSwitch()
    assert not ks.active
    ks.engage()
    assert ks.active
    ks.release()
    assert not ks.active


def test_kill_switch_halts_hermes_actions():
    ks = KillSwitch()
    h = Hermes(dry_run=True, kill_switch=ks)
    assert h.run_shell("ls").ok          # runs while released
    ks.engage()
    r = h.run_shell("ls")
    assert not r.ok and "hold" in r.summary.lower()
    assert not h.open_url("example.com").ok


def test_kill_switch_short_circuits_brain_turn():
    ks = KillSwitch()
    ks.engage()

    class BoomClient:  # must never be called while paused
        def __init__(self):
            self.messages = SimpleNamespace(create=self._boom)

        def _boom(self, **k):
            raise AssertionError("model called while paused")

    brain = DonaldBrain(client=BoomClient(), hermes=Hermes(dry_run=True), kill_switch=ks)
    result = brain.take_turn("do something")
    assert "hold" in result.reply.lower()
    assert result.actions == []


# -- context sensing ---------------------------------------------------------

def test_gather_and_format_context():
    ctx = gather_context(now=datetime(2026, 7, 1, 9, 30), platform="linux")
    assert ctx["platform"] == "linux"
    assert "2026-07-01" in ctx["time"]
    text = format_context(ctx)
    assert "ambient context" in text.lower()
    assert "linux" in text


def test_context_injected_into_system_prompt():
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")], stop_reason="end_turn")

    class FakeClient:
        def __init__(self):
            self.calls = []
            self.messages = SimpleNamespace(create=self._c)

        def _c(self, **k):
            self.calls.append(k)
            return resp

    brain = DonaldBrain(client=FakeClient(), hermes=Hermes(dry_run=True), personality_text="P")
    brain.take_turn("hey")
    system = brain.client.calls[0]["system"]
    # personality + operator briefing + ambient context.
    assert any("ambient context" in b["text"].lower() for b in system)


# -- proactivity -------------------------------------------------------------

def test_reminder_fires_when_due_not_before():
    said = []
    eng = ProactiveEngine(sink=said.append)
    eng.schedule(due_at=100.0, message="call Luca")
    assert eng.due(now=50.0) == []          # not yet
    lines = eng.due(now=100.0)
    assert len(lines) == 1 and "call Luca" in lines[0]
    assert eng.due(now=200.0) == []          # fired once, gone


def test_kill_switch_holds_reminders():
    ks = KillSwitch()
    eng = ProactiveEngine(sink=lambda x: None, kill_switch=ks)
    eng.schedule(due_at=10.0, message="stretch")
    ks.engage()
    assert eng.due(now=20.0) == []           # held while paused
    assert eng.pending == 1
    ks.release()
    assert len(eng.due(now=20.0)) == 1       # delivered after resume


def test_set_reminder_tool_schedules_through_hermes():
    scheduled = []
    h = Hermes(dry_run=True, reminder_sink=lambda s, m: scheduled.append((s, m)))
    r = h.set_reminder(600, "call Luca")
    assert r.ok and scheduled == [(600.0, "call Luca")]
    # Without a sink wired, it fails gracefully rather than pretending.
    assert not Hermes(dry_run=True).set_reminder(600, "x").ok
