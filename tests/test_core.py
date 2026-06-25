"""Verification for the headless tiers: text loop, tools, memory, safety.

These run with the offline mock brain and a temp database, so they need no API
keys and prove each tier works on its own.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from donald.agent import Agent
from donald.brain import MockBrain
from donald.config import Config
from donald.memory import Memory
from donald.safety import SafetyGate, install_safety
from donald.tools import Registry, register_all
from donald.tools.base import ToolError


def make_config(tmp_path: Path) -> Config:
    return Config(
        brain="mock",
        model="mock",
        anthropic_api_key=None,
        deepgram_api_key=None,
        elevenlabs_api_key=None,
        elevenlabs_voice_id="x",
        brave_api_key=None,
        db_path=tmp_path / "donald.db",
        workspace=tmp_path / "ws",
        proactive_enabled=False,
        proactive_interval=60,
    )


class Ctx:
    def __init__(self, config, memory):
        self.config = config
        self.memory = memory


def build_agent(tmp_path: Path, unattended=False, interactive=False):
    config = make_config(tmp_path)
    config.ensure_dirs()
    memory = Memory(config.db_path)
    reg = Registry()
    reg.context = Ctx(config, memory)
    register_all(reg)
    install_safety(reg, config, unattended=unattended, interactive=interactive)
    agent = Agent(MockBrain(config), reg, system="test")
    return agent, reg, memory


# ── Tier 0: text loop ──────────────────────────────────────────────────────
def test_tier0_text_loop_replies(tmp_path):
    agent, _, _ = build_agent(tmp_path)
    msgs = [{"role": "user", "content": "hello there"}]
    reply = agent.respond(msgs)
    assert "hello there" in reply.lower() or "donald" in reply.lower()
    assert msgs[-1]["role"] == "assistant"


# ── Tier 1: tools ──────────────────────────────────────────────────────────
def test_tier1_registry_has_all_tools(tmp_path):
    _, reg, _ = build_agent(tmp_path)
    for name in ("get_time", "set_reminder", "web_search", "read_file",
                 "write_file", "run_shell", "remember", "recall", "forget"):
        assert name in reg, f"missing tool {name}"


def test_tier1_time_tool_via_agent(tmp_path):
    agent, _, _ = build_agent(tmp_path)
    msgs = [{"role": "user", "content": "what time is it"}]
    reply = agent.respond(msgs)
    assert "UTC" in reply or "Local" in reply


def test_tier1_shell_confined_to_workspace(tmp_path):
    _, reg, _ = build_agent(tmp_path)
    out = reg.dispatch("read_file", {"path": "../../../etc/passwd"})
    assert "outside the workspace" in out.lower()


def test_tier1_write_then_read(tmp_path):
    _, reg, _ = build_agent(tmp_path)
    assert "Wrote" in reg.dispatch("write_file", {"path": "note.txt", "content": "hi"})
    assert reg.dispatch("read_file", {"path": "note.txt"}) == "hi"


# ── Tier 3: memory persistence ─────────────────────────────────────────────
def test_tier3_memory_survives_restart(tmp_path):
    config = make_config(tmp_path)
    config.ensure_dirs()
    m1 = Memory(config.db_path)
    m1.add_fact("the user is vegetarian", "food")
    m1.close()
    # New process simulation: fresh Memory on same file.
    m2 = Memory(config.db_path)
    facts = m2.search_facts("vegetarian")
    assert facts and "vegetarian" in facts[0].content


def test_tier3_remember_tool_persists(tmp_path):
    agent, _, memory = build_agent(tmp_path)
    msgs = [{"role": "user", "content": "remember I love sailing"}]
    agent.respond(msgs)
    assert any("sailing" in f.content for f in memory.list_facts())


def test_tier3_reminders_due(tmp_path):
    config = make_config(tmp_path)
    config.ensure_dirs()
    m = Memory(config.db_path)
    m.add_reminder("past thing", "2000-01-01T00:00:00+00:00")
    m.add_reminder("future thing", "2999-01-01T00:00:00+00:00")
    due = m.due_reminders()
    assert len(due) == 1 and due[0].text == "past thing"


# ── Tier 5: safety ─────────────────────────────────────────────────────────
def test_tier5_hard_block_rm_rf(tmp_path):
    _, reg, _ = build_agent(tmp_path)
    out = reg.dispatch("run_shell", {"command": "rm -rf /"})
    assert "blocked by safety" in out.lower() or "forbidden" in out.lower()


def test_tier5_unattended_denies_mutating(tmp_path):
    _, reg, _ = build_agent(tmp_path, unattended=True)
    out = reg.dispatch("write_file", {"path": "x.txt", "content": "y"})
    assert "unattended" in out.lower()


def test_tier5_readonly_passes_in_unattended(tmp_path):
    _, reg, _ = build_agent(tmp_path, unattended=True)
    out = reg.dispatch("get_time", {})
    assert "UTC" in out or "Local" in out


def test_tier5_audit_log_records(tmp_path):
    _, reg, _ = build_agent(tmp_path, unattended=True)
    reg.dispatch("get_time", {})
    gate = reg.safety_gate
    assert isinstance(gate, SafetyGate)
    assert gate.audit_log and gate.audit_log[-1]["tool"] == "get_time"
