"""Tests for the command-center state: action log + reminder snapshot.

Constructs the real server on an ephemeral port (no serving loop) and drives its
state methods directly — no HTTP, no threads left running.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donald.app import _DonaldServer, _Handler  # noqa: E402
from donald.brain import TurnResult  # noqa: E402
from donald.killswitch import KillSwitch  # noqa: E402
from donald.proactive import ProactiveEngine  # noqa: E402


class _StubBrain:
    hermes = None
    memory = None


def _server():
    ks = KillSwitch()
    pro = ProactiveEngine(sink=lambda x: None, kill_switch=ks)
    # Port 0 => OS picks a free port; we never call serve_forever.
    return _DonaldServer(("127.0.0.1", 0), _Handler, _StubBrain(), ks, pro), pro


def test_record_turn_logs_actions_newest_first():
    srv, _ = _server()
    try:
        srv.record_turn("do a", TurnResult(reply="ok", actions=[{"action": "run_shell", "ok": True}]))
        srv.record_turn("do b", TurnResult(reply="ok", actions=[{"action": "open_url", "ok": True}]))
        recent = srv.recent_actions()
        assert srv.turn_count == 2
        assert [a["action"] for a in recent] == ["open_url", "run_shell"]  # newest first
        assert all("ts" in a and "transcript" in a for a in recent)
    finally:
        srv.server_close()


def test_action_log_is_bounded():
    srv, _ = _server()
    try:
        for i in range(150):
            srv.record_turn("x", TurnResult(reply="", actions=[{"action": f"a{i}", "ok": True}]))
        assert len(srv.action_log) == 100  # deque maxlen caps memory growth
    finally:
        srv.server_close()


def test_reminder_snapshot_orders_and_counts_down():
    pro = ProactiveEngine(sink=lambda x: None)
    pro.schedule(due_at=200.0, message="later")
    pro.schedule(due_at=110.0, message="soon")
    snap = pro.snapshot(now=100.0)
    assert [r["message"] for r in snap] == ["soon", "later"]  # soonest first
    assert snap[0]["in_seconds"] == 10.0
