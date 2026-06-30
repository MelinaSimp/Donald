"""Tests for Hermes — the computer-control engine.

All run offline: dry-run mode means nothing actually executes, and the safety
assertions exercise the wired-in ApprovalGate without touching the disk.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donald.hermes import Hermes, TOOL_SPECS, dispatch  # noqa: E402
from donald.hermes.engine import detect_platform  # noqa: E402


def test_dry_run_shell_does_not_execute():
    h = Hermes(dry_run=True)
    r = h.run_shell("echo hello")
    assert r.ok
    assert "[dry-run]" in r.summary
    assert "echo hello" in r.summary


def test_empty_command_is_rejected():
    r = Hermes(dry_run=True).run_shell("   ")
    assert not r.ok


def test_hardline_command_is_blocked_unconditionally():
    h = Hermes(dry_run=True)
    r = h.run_shell("rm -rf /")
    assert not r.ok
    assert not r.needs_confirmation  # hardline is a hard no, not a confirm
    # Even an explicit confirm cannot override the hardline blocklist.
    r2 = h.run_shell("rm -rf /", confirmed=True)
    assert not r2.ok and not r2.needs_confirmation


def test_risky_command_requires_confirmation_then_runs():
    h = Hermes(dry_run=True)
    r = h.run_shell("git push --force")
    assert not r.ok
    assert r.needs_confirmation
    assert r.confirm_token
    # Approving runs it (dry-run, so it just echoes the intent).
    done = h.confirm(r.confirm_token)
    assert done.ok
    assert "git push --force" in done.summary
    # Token is single-use.
    again = h.confirm(r.confirm_token)
    assert not again.ok


def test_safe_command_runs_without_confirmation():
    h = Hermes(dry_run=True)
    r = h.run_shell("ls -la")
    assert r.ok
    assert not r.needs_confirmation


def test_open_url_normalises_scheme():
    h = Hermes(dry_run=True)
    r = h.open_url("example.com")
    assert r.ok
    assert "https://example.com" in r.summary


def test_open_app_builds_platform_command():
    for plat, needle in (("macos", "open -a"), ("windows", "start"), ("linux", "gtk-launch")):
        h = Hermes(dry_run=True, platform=plat)
        r = h.open_app("Safari")
        assert r.ok
        assert needle in r.summary or "Safari" in r.summary


def test_dispatch_routes_to_engine():
    h = Hermes(dry_run=True)
    r = dispatch(h, "open_url", {"url": "openai.com"})
    assert r.ok
    unknown = dispatch(h, "nope", {})
    assert not unknown.ok


def test_tool_specs_are_well_formed():
    names = {t["name"] for t in TOOL_SPECS}
    assert {"run_shell", "open_app", "open_url", "confirm_action"} <= names
    for spec in TOOL_SPECS:
        assert "description" in spec and spec["description"]
        assert spec["input_schema"]["type"] == "object"


def test_detect_platform_is_known():
    assert detect_platform() in {"macos", "windows", "linux"}
