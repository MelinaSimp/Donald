"""Tests for Donald's tools: path safety, read/write/edit, shell, allowlist."""

import importlib

import pytest

import donald.tools as tools


def _fresh():
    importlib.reload(tools)
    return tools


def test_read_file(workdir, home):
    t = _fresh()
    (workdir / "a.txt").write_text("hello")
    out, err = t.execute("read_file", {"path": "a.txt"})
    assert not err and out == "hello"


def test_read_missing(workdir, home):
    t = _fresh()
    out, err = t.execute("read_file", {"path": "nope.txt"})
    assert err and "No such file" in out


def test_write_file(workdir, home):
    t = _fresh()
    out, err = t.execute("write_file", {"path": "out.txt", "content": "data"})
    assert not err
    assert (workdir / "out.txt").read_text() == "data"


@pytest.mark.parametrize("escape", ["../escape.txt", "/etc/passwd"])
def test_path_escape_rejected(workdir, home, escape):
    t = _fresh()
    out, err = t.execute("read_file", {"path": escape})
    assert err and "escapes" in out


def test_edit_file_unique(workdir, home):
    t = _fresh()
    (workdir / "f.txt").write_text("alpha beta gamma")
    out, err = t.execute("edit_file", {"path": "f.txt", "old": "beta", "new": "BETA"})
    assert not err
    assert (workdir / "f.txt").read_text() == "alpha BETA gamma"


def test_edit_file_ambiguous_rejected(workdir, home):
    t = _fresh()
    (workdir / "f.txt").write_text("x x")
    out, err = t.execute("edit_file", {"path": "f.txt", "old": "x", "new": "y"})
    assert err and "2 times" in out
    assert (workdir / "f.txt").read_text() == "x x"  # unchanged


def test_edit_file_missing_snippet(workdir, home):
    t = _fresh()
    (workdir / "f.txt").write_text("hello")
    out, err = t.execute("edit_file", {"path": "f.txt", "old": "absent", "new": "y"})
    assert err and "not found" in out


def test_run_shell_reports_exit_and_output(workdir, home):
    t = _fresh()
    out, err = t.execute("run_shell", {"command": "echo hi"})
    assert not err
    assert "exit code 0" in out and "hi" in out


def test_run_shell_nonzero_is_not_error(workdir, home):
    t = _fresh()
    out, err = t.execute("run_shell", {"command": "exit 3"})
    assert not err  # a non-zero exit is informative, not a tool failure
    assert "exit code 3" in out


def test_unknown_tool(workdir, home):
    t = _fresh()
    out, err = t.execute("does_not_exist", {})
    assert err and "Unknown tool" in out


def test_auto_approved_uses_allowlist(workdir, home, monkeypatch):
    monkeypatch.setenv("DONALD_SHELL_AUTO_APPROVE", "ls,git status")
    t = _fresh()  # reload picks up env-driven CONFIG
    assert t.auto_approved("run_shell", {"command": "ls -la"}) is True
    assert t.auto_approved("run_shell", {"command": "rm -rf /"}) is False
    assert t.auto_approved("write_file", {"path": "x"}) is False


def test_registry_and_approval_set(workdir, home):
    t = _fresh()
    names = {tool.get("name") for tool in t.ALL_TOOLS}
    assert {"read_file", "write_file", "edit_file", "run_shell", "remember", "update_memory"} <= names
    assert t.REQUIRES_APPROVAL == {"write_file", "edit_file", "run_shell"}
