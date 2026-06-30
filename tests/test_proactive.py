"""Verification for Tier 4 (proactive loop) and its Tier 5 safety coupling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from donald.memory import Memory
from donald.proactive import ProactiveLoop, reminder_trigger
from tests.test_core import build_agent  # reuse the headless rig


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def test_due_reminder_fires_once(tmp_path):
    m = Memory(tmp_path / "d.db")
    m.add_reminder("call the dentist", _past())
    m.add_reminder("not yet", _future())

    sent: list[str] = []
    loop = ProactiveLoop(memory=m, notifier=sent.append)

    loop.tick()
    assert sent == ["Reminder: call the dentist"]

    # Second tick must NOT nag again — trigger fired once.
    loop.tick()
    assert sent == ["Reminder: call the dentist"]


def test_check_is_pure_function(tmp_path):
    m = Memory(tmp_path / "d.db")
    m.add_reminder("breathe", _past())
    loop = ProactiveLoop(memory=m, notifier=lambda _: None)
    msgs = loop.check()
    assert msgs == ["Reminder: breathe"]


def test_broken_trigger_does_not_crash_loop(tmp_path):
    m = Memory(tmp_path / "d.db")

    def boom(_memory):
        raise ValueError("kaboom")

    loop = ProactiveLoop(memory=m, notifier=lambda _: None, triggers=[boom])
    msgs = loop.check()
    assert msgs and "background check failed" in msgs[0]


def test_unattended_agent_cannot_mutate(tmp_path):
    # The proactive context runs unattended; mutating tools must be denied even
    # if the brain asks for them.
    _, reg, _ = build_agent(tmp_path, unattended=True)
    assert "unattended" in reg.dispatch("write_file", {"path": "x", "content": "y"}).lower()
    assert "unattended" in reg.dispatch("remember", {"content": "z"}).lower()
    # ...but reading is still fine.
    assert "UTC" in reg.dispatch("get_time", {}) or "Local" in reg.dispatch("get_time", {})
