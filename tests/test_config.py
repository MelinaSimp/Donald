"""Tests for Donald's configuration loading and the shell allowlist."""

import importlib
import json

import donald.config as config


def _fresh():
    importlib.reload(config)
    return config


def test_defaults(home):
    c = _fresh()
    cfg = c.load()
    assert cfg.model == "claude-opus-4-8"
    assert cfg.shell_timeout_s == 60
    assert cfg.shell_auto_approve == ()
    assert cfg.voice is False


def test_file_overrides_defaults(home):
    (home / ".donald").mkdir()
    (home / ".donald" / "config.json").write_text(
        json.dumps({"shell_timeout_s": 5, "shell_auto_approve": ["git status", "ls"]})
    )
    c = _fresh()
    cfg = c.load()
    assert cfg.shell_timeout_s == 5
    assert cfg.shell_auto_approve == ("git status", "ls")


def test_unknown_keys_ignored(home):
    (home / ".donald").mkdir()
    (home / ".donald" / "config.json").write_text(json.dumps({"bogus": 1, "model": "x"}))
    cfg = _fresh().load()
    assert cfg.model == "x"
    assert not hasattr(cfg, "bogus")


def test_malformed_file_falls_back(home):
    (home / ".donald").mkdir()
    (home / ".donald" / "config.json").write_text("{ not json ")
    cfg = _fresh().load()  # must not raise
    assert cfg.model == "claude-opus-4-8"


def test_env_overrides_file(home, monkeypatch):
    (home / ".donald").mkdir()
    (home / ".donald" / "config.json").write_text(json.dumps({"shell_timeout_s": 5}))
    monkeypatch.setenv("DONALD_SHELL_TIMEOUT", "99")
    monkeypatch.setenv("DONALD_VOICE", "true")
    monkeypatch.setenv("DONALD_SHELL_AUTO_APPROVE", "ls, cat ,git status")
    cfg = _fresh().load()
    assert cfg.shell_timeout_s == 99
    assert cfg.voice is True
    assert cfg.shell_auto_approve == ("ls", "cat", "git status")


def test_bad_int_env_keeps_current(home, monkeypatch):
    monkeypatch.setenv("DONALD_MAX_TOKENS", "not-a-number")
    cfg = _fresh().load()
    assert cfg.max_tokens == 4096


def test_shell_auto_approved_prefix_match(home):
    c = _fresh()
    cfg = c.Config(shell_auto_approve=("git status", "ls"))
    assert c.shell_auto_approved("ls -la", cfg) is True
    assert c.shell_auto_approved("git status -s", cfg) is True
    assert c.shell_auto_approved("rm -rf /", cfg) is False
    assert c.shell_auto_approved("  ls", cfg) is True  # leading space tolerated
