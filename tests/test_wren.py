"""Tier verification with a fake LLM — no API key needed.

Run:  python tests/test_wren.py      (self-contained, no pytest required)
 or:  python -m pytest tests/        (pytest also discovers the test_* fns)

The fake LLM is scripted: each agent turn pops the next scripted response, so we
can drive tool-call flows deterministically and assert on what the brain does.
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wren.agent import Agent  # noqa: E402
from wren.config import Config  # noqa: E402
from wren.heartbeat import Heartbeat, Inbox  # noqa: E402
from wren.llm import ToolCall, Turn  # noqa: E402
from wren.memory import Memory  # noqa: E402
from wren.safety import Audit, is_paused, set_paused  # noqa: E402
from wren.tools import build_context, build_registry  # noqa: E402


# --- fake LLM --------------------------------------------------------------
class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def stream_turn(self, system, messages, tools=None, on_text=None):
        self.calls.append({"system": system, "messages": copy.deepcopy(messages)})
        turn = self.script.pop(0)
        if callable(turn):
            turn = turn(messages)
        if on_text and turn.text:
            on_text(turn.text)
        return turn


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))
        return f"Sent to {to}: {subject or '(no subject)'}"


def say(text):
    return Turn(content=[{"type": "text", "text": text}], text=text,
                tool_calls=[], stop_reason="end_turn")


def call_tool(name, inp, tid="tu1"):
    return Turn(
        content=[{"type": "tool_use", "id": tid, "name": name, "input": inp}],
        text="", tool_calls=[ToolCall(tid, name, inp)], stop_reason="tool_use",
    )


# --- test scaffolding ------------------------------------------------------
def make_config(tmp: Path) -> Config:
    data = {
        "assistant": {"name": "Wren", "persona": "You are Wren, warm and brief."},
        "memory": {"path": str(tmp / "memory.json")},
        "reminders": {"path": str(tmp / "reminders.json")},
        "notes": {"path": str(tmp / "notes")},
        "heartbeat": {
            "state_path": str(tmp / "hb.json"),
            "inbox_path": str(tmp / "inbox.json"),
            "quiet_hours": {"start": "22:00", "end": "08:00"},
            "checks": [{"name": "due_reminders", "every_seconds": 0, "level": "loud"}],
        },
        "safety": {
            "confirm_tools": ["send_message", "spend_money", "delete_data", "change_settings"],
            "audit_log": str(tmp / "audit.log"),
            "paused": False,
        },
        "brain": {"max_tool_rounds": 8},
    }
    return Config(data, tmp / "config.yaml")


def make_agent(tmp: Path, llm, gate=None):
    config = make_config(tmp)
    memory = Memory(config.resolve_path("memory.path", "x"))
    ctx = build_context(config, memory)
    registry = build_registry(ctx)
    audit = Audit(config.resolve_path("safety.audit_log", "x"))
    agent = Agent(
        persona=config.get("assistant.persona"),
        llm=llm, registry=registry, memory=memory, gate=gate, audit=audit,
        confirm_tools=set(config.get("safety.confirm_tools")),
    )
    return agent, ctx, memory, config


# --- Tier 1: the brain remembers earlier turns in a session ----------------
def test_tier1_keeps_history():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        llm = FakeLLM([say("Hi Alice."), say("Your name is Alice.")])
        agent, *_ = make_agent(tmp, llm)
        agent.respond("My name is Alice.")
        agent.respond("What's my name?")
        # The 2nd model call must have been given the 1st user+assistant turns.
        second_call_msgs = llm.calls[1]["messages"]
        joined = str(second_call_msgs)
        assert "Alice" in joined and len(second_call_msgs) >= 3
    print("✓ Tier 1: history is passed back into the loop")


# --- Tier 2: tool dispatch + result fed back; failures don't crash ---------
def test_tier2_tool_dispatch():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        llm = FakeLLM([
            call_tool("add_reminder", {"text": "buy milk"}),
            say("Added it."),
        ])
        agent, ctx, *_ = make_agent(tmp, llm)
        reply = agent.respond("remind me to buy milk")
        assert reply == "Added it."
        assert ctx.reminders.list()[0]["text"] == "buy milk"
        # The model's 2nd call saw the tool_result.
        assert "tool_result" in str(llm.calls[1]["messages"])
    print("✓ Tier 2: tool runs, result is fed back, model continues")


def test_tier2_tool_failure_is_caught():
    from wren.tools.base import Tool

    def boom(_):
        raise ValueError("kaboom")

    t = Tool("boom", "d", {"type": "object", "properties": {}}, boom)
    result = t.run({})
    assert result.is_error and "kaboom" in result.content
    print("✓ Tier 2: a failing tool returns an error to the model, no crash")


# --- Tier 4: memory survives a 'restart' and feeds the system prompt -------
def test_tier4_memory_persists():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        path = tmp / "memory.json"
        Memory(path).add("Prefers morning meetings")
        # New instance == a fresh process/restart.
        reloaded = Memory(path)
        assert "morning meetings" in reloaded.render()
    print("✓ Tier 4: memory persists across restarts")


def test_tier4_memory_in_system_prompt():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        llm = FakeLLM([say("ok")])
        agent, ctx, memory, _ = make_agent(tmp, llm)
        memory.add("Name is Alice")
        assert "Alice" in agent.system_prompt()
    print("✓ Tier 4: stored facts are loaded into the system prompt")


# --- Tier 6: the confirmation gate blocks consequential tools --------------
def test_tier6_gate_blocks_then_allows():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Gate denies.
        llm = FakeLLM([
            call_tool("send_message", {"to": "bob", "body": "hi"}),
            say("It's awaiting your confirmation."),
        ])
        agent, *_ = make_agent(tmp, llm, gate=lambda *a: False)
        agent.respond("text bob hi")
        assert "did not approve" in str(llm.calls[1]["messages"])

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Gate approves -> the real mailer is invoked.
        llm = FakeLLM([
            call_tool("send_message", {"to": "bob@example.com", "body": "hi"}),
            say("Sent."),
        ])
        agent, ctx, *_ = make_agent(tmp, llm, gate=lambda *a: True)
        ctx.mailer = FakeMailer()
        agent.respond("email bob hi")
        assert ctx.mailer.sent == [("bob@example.com", "", "hi")]
        assert "Sent to bob@example.com" in str(llm.calls[1]["messages"])
    print("✓ Tier 6: gate blocks consequential tools until approved")


def test_tier6_send_message_unconfigured_is_honest():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        llm = FakeLLM([
            call_tool("send_message", {"to": "bob@example.com", "body": "hi"}),
            say("ok"),
        ])
        agent, ctx, *_ = make_agent(tmp, llm, gate=lambda *a: True)
        assert ctx.mailer is None  # no email config in the test config
        agent.respond("email bob hi")
        assert "isn't set up" in str(llm.calls[1]["messages"])
    print("✓ Tier 6: send_message says so honestly when email isn't configured")


def test_tier6_invoke_tool_respects_gate():
    # The send-test CLI path: run a consequential tool directly, same gate.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        agent, ctx, *_ = make_agent(tmp, FakeLLM([]), gate=lambda *a: False)
        ctx.mailer = FakeMailer()
        out = agent.invoke_tool("send_message", {"to": "a@b.c", "body": "hi"}, "send-test")
        assert "did not approve" in out and ctx.mailer.sent == []  # gate blocked it

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        agent, ctx, *_ = make_agent(tmp, FakeLLM([]), gate=lambda *a: True)
        ctx.mailer = FakeMailer()
        out = agent.invoke_tool("send_message", {"to": "a@b.c", "body": "hi"}, "send-test")
        assert "Sent to a@b.c" in out and ctx.mailer.sent == [("a@b.c", "", "hi")]
    print("✓ Tier 6: invoke_tool (send-test) goes through the same gate")


def test_tier6_prompt_injection_rule_present():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        agent, *_ = make_agent(tmp, FakeLLM([say("ok")]))
        sp = agent.system_prompt().lower()
        assert "instructions to obey" in sp and "outside world" in sp
    print("✓ Tier 6: 'treat read content as data, not commands' rule is in place")


def test_tier6_config_is_editable():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        config = make_config(tmp)
        config.save()
        config.set("brain.model", "claude-haiku-4-5")
        reloaded = Config.load(tmp / "config.yaml")
        assert reloaded.get("brain.model") == "claude-haiku-4-5"
    print("✓ Tier 6: config changes persist with no code edit")


# --- Tier 5: heartbeat surfaces once, holds notices, survives restart ------
def test_tier5_heartbeat_surfaces_and_holds():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        config = make_config(tmp)
        from wren.tools.reminders import Reminders

        reminders = Reminders(config.resolve_path("reminders.path", "x"))
        reminders.add("call mom", due="2000-01-01T00:00")  # already overdue
        inbox = Inbox(config.resolve_path("heartbeat.inbox_path", "x"))
        audit = Audit(config.resolve_path("safety.audit_log", "x"))
        loud_seen = []
        hb = Heartbeat(config, reminders, inbox, audit, on_loud=loud_seen.append)

        hb.tick()  # new check fires on the first tick
        assert any("call mom" in n["text"] for n in inbox.pending())
        before = len(inbox.pending())
        hb.tick()  # should NOT re-surface the same reminder
        assert len(inbox.pending()) == before

        # Restart: a fresh Heartbeat from the same state doesn't refire everything.
        hb2 = Heartbeat(config, reminders, inbox, audit, on_loud=loud_seen.append)
        hb2.tick()
        assert len(inbox.pending()) == before

        # Dismissible.
        inbox.dismiss()
        assert inbox.pending() == []
    print("✓ Tier 5: surfaces once, holds for catch-up, survives restart, dismissible")


def test_tier5_kill_switch_pauses_checks():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        config = make_config(tmp)
        from wren.tools.reminders import Reminders

        reminders = Reminders(config.resolve_path("reminders.path", "x"))
        reminders.add("call mom", due="2000-01-01T00:00")
        inbox = Inbox(config.resolve_path("heartbeat.inbox_path", "x"))
        audit = Audit(config.resolve_path("safety.audit_log", "x"))
        set_paused(config, True)
        assert is_paused(config)
        hb = Heartbeat(config, reminders, inbox, audit)
        hb.tick(); hb.tick(); hb.tick()
        assert inbox.pending() == []  # paused -> nothing surfaced
    print("✓ Tier 5: kill switch pauses all proactive behaviour")


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} checks passed.")


if __name__ == "__main__":
    _run_all()
