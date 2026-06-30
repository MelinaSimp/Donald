"""CI-friendly tests for all six tiers. No API key required.

Mirrors the invariants verified by the demo_*.py scripts, driven by scripted
fake LLMs from conftest.py.
"""

from __future__ import annotations

import json

import pytest
from conftest import EchoLLM, ScriptedLLM, text_response, tool_response

from orchestrator import (
    Agent,
    AgentManifest,
    AgentResult,
    AgentRuntime,
    AllowAll,
    CallbackApprover,
    CallbackHandoffApprover,
    DenyAll,
    EventEmitter,
    HandoffRecommendation,
    ManifestStore,
    ManifestWatcher,
    Orchestrator,
    Tool,
    build_default_registry,
    dispatch_tool_name,
)
from orchestrator.handoff import parse_handoff


# --- Tier 2: least privilege + bounded execution ----------------------------

def test_view_exposes_only_allowlist():
    reg = build_default_registry()
    agent = Agent(
        AgentManifest(name="a", system_prompt="x", allowed_tools=["calculator"]), reg
    )
    assert {s["name"] for s in agent.tools.schemas()} == {"calculator"}


def test_out_of_scope_tool_is_blocked():
    reg = build_default_registry()
    agent = Agent(
        AgentManifest(name="a", system_prompt="x", allowed_tools=["calculator"]), reg
    )
    with pytest.raises(PermissionError):
        agent.tools.get("word_count")


def test_invalid_allowlist_fails_at_construction():
    with pytest.raises(KeyError):
        Agent(AgentManifest(name="a", system_prompt="x", allowed_tools=["nope"]),
              build_default_registry())


def test_bounded_loop_returns_not_converged():
    # An LLM that asks for a tool forever must stop at max_iterations.
    reg = build_default_registry()
    llm = ScriptedLLM(script=[], default=tool_response("calculator", {"expression": "1+1"}))
    agent = Agent(
        AgentManifest(name="a", system_prompt="x", allowed_tools=["calculator"],
                      max_iterations=3),
        reg, llm=llm,
    )
    result = agent.run("loop")
    assert result.converged is False
    assert result.iterations == 3 and llm.calls == 3


def test_loop_converges_on_end_turn():
    reg = build_default_registry()
    agent = Agent(
        AgentManifest(name="a", system_prompt="x"),
        reg, llm=ScriptedLLM([text_response("the answer")]),
    )
    result = agent.run("q")
    assert result.converged and result.output == "the answer"


# --- Tier 3: failure isolation ----------------------------------------------

def _boom(_):
    raise RuntimeError("kaboom")


def test_tool_boundary_boxes_handler_exception():
    reg = build_default_registry()
    reg.register(Tool("explode", "fails", {"type": "object", "properties": {}}, _boom))
    agent = Agent(AgentManifest(name="a", system_prompt="x", allowed_tools=["explode"]), reg)
    res = agent._execute_tool_call("explode", {}, "tu1")
    assert res["is_error"] and "kaboom" in res["content"]


def test_observer_failure_is_swallowed():
    seen = []
    emitter = EventEmitter([
        lambda e, p: (_ for _ in ()).throw(ValueError("bad")),
        lambda e, p: seen.append(e),
    ])
    emitter.emit("ping", n=1)  # must not raise
    assert seen == ["ping"]


def test_subagent_failure_is_boxed():
    orch = Orchestrator(build_default_registry())

    class Boom:
        def run(self, task):
            raise RuntimeError("crashed")

    orch._agents["boom"] = Boom()
    res = orch._safe_run("boom", "t")
    assert isinstance(res, AgentResult) and not res.converged
    assert res.error and "crashed" in res.error


# --- Tier 4: confirmation gates ---------------------------------------------

def _email_registry(sink):
    reg = build_default_registry()
    reg.register(
        Tool(
            "send_email", "irreversible",
            {"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]},
            lambda inp: (sink.append(inp), "sent")[1],
            requires_confirmation=True,
        )
    )
    return reg


def test_gated_tool_denied_by_default():
    sink = []
    agent = Agent(
        AgentManifest(name="m", system_prompt="x", allowed_tools=["send_email"]),
        _email_registry(sink),
    )  # default DenyAll
    res = agent._execute_tool_call("send_email", {"to": "x"}, "tu1")
    body = json.loads(res["content"])
    assert body["confirmation_required"] and body["status"] == "not_executed"
    assert sink == []


def test_gated_tool_runs_once_after_approval():
    sink = []
    agent = Agent(
        AgentManifest(name="m", system_prompt="x", allowed_tools=["send_email"]),
        _email_registry(sink), approver=AllowAll(),
    )
    res = agent._execute_tool_call("send_email", {"to": "x"}, "tu1")
    assert res["content"] == "sent" and sink == [{"to": "x"}]


def test_execute_confirmed_bypasses_gate():
    sink = []
    agent = Agent(
        AgentManifest(name="m", system_prompt="x", allowed_tools=["send_email"]),
        _email_registry(sink),
    )
    assert agent.execute_confirmed("send_email", {"to": "x"}) == "sent"
    assert sink == [{"to": "x"}]


def test_policy_approver_denies_by_input():
    sink = []
    agent = Agent(
        AgentManifest(name="m", system_prompt="x", allowed_tools=["send_email"]),
        _email_registry(sink),
        approver=CallbackApprover(lambda req: req.tool_input["to"] != "vp"),
    )
    res = agent._execute_tool_call("send_email", {"to": "vp"}, "tu1")
    assert json.loads(res["content"])["confirmation_required"] and sink == []


# --- Tier 5: handoffs --------------------------------------------------------

def test_handoff_rejects_inline_blob():
    with pytest.raises(ValueError):
        parse_handoff("a", {"target_agent": "b", "task": "t", "artifacts": {"s": "x\n" * 1000}})


def test_handoff_accepts_references():
    rec = parse_handoff("a", {"target_agent": "b", "task": "t",
                              "artifacts": {"s": "s3://bucket/x", "id": "JIRA-1"}})
    assert rec.artifacts == {"s": "s3://bucket/x", "id": "JIRA-1"}


def _orch_with_spy():
    orch = Orchestrator(build_default_registry())
    orch.register_agent(AgentManifest(name="eng", system_prompt="x"))

    class Spy:
        def __init__(self):
            self.runs = []

        def run(self, task):
            self.runs.append(task)
            return AgentResult(agent="eng", output="ok", iterations=1, converged=True)

    spy = Spy()
    orch._agents["eng"] = spy
    return orch, spy


def _rec():
    return HandoffRecommendation(source_agent="s", target_agent="eng",
                                 reason="r", task="do it", confidence=0.9)


def test_offer_does_not_dispatch():
    orch, spy = _orch_with_spy()
    text = orch.offer(_rec())
    assert "eng" in text and spy.runs == []


def test_review_holds_for_human_by_default():
    orch, spy = _orch_with_spy()
    accepted, result = orch.review_handoff(_rec())
    assert accepted is False and result is None and spy.runs == []


def test_review_dispatches_once_on_approval():
    orch, spy = _orch_with_spy()
    accepted, result = orch.review_handoff(_rec(), CallbackHandoffApprover(lambda r: True))
    assert accepted is True and result is not None and spy.runs == ["do it"]


# --- Tier 6: hot-reload ------------------------------------------------------

def _write(directory, name, **extra):
    (directory / f"{name}.json").write_text(
        json.dumps({"name": name, "system_prompt": f"You are {name}.", **extra})
    )


def test_hot_add_and_retire(tmp_path):
    _write(tmp_path, "engineer", allowed_tools=["calculator"])
    reg = build_default_registry()
    runtime = AgentRuntime(reg, llm=EchoLLM())
    watcher = ManifestWatcher(ManifestStore(tmp_path), runtime)

    assert watcher.poll().added == ["engineer"]
    assert watcher.poll() is None  # no-op when unchanged

    _write(tmp_path, "designer")
    change = watcher.poll()
    assert "designer" in change.added
    name = dispatch_tool_name("designer")
    assert reg.has(name)
    # immediately callable
    assert "handled: mock" in reg.get(name).handler({"task": "mock"})

    _write(tmp_path, "designer", active=False)
    change = watcher.poll()
    assert "designer" in change.removed and not reg.has(name)


def test_invalid_manifest_is_skipped(tmp_path):
    _write(tmp_path, "ok", allowed_tools=["calculator"])
    _write(tmp_path, "bad", allowed_tools=["does_not_exist"])
    runtime = AgentRuntime(build_default_registry(), llm=EchoLLM())
    change = ManifestWatcher(ManifestStore(tmp_path), runtime).poll()
    assert "ok" in change.added and "bad" in change.invalid
    assert "ok" in runtime.roster() and "bad" not in runtime.roster()


def test_serve_loop_applies_changes(tmp_path):
    from orchestrator import serve

    _write(tmp_path, "engineer", allowed_tools=["calculator"])
    runtime = AgentRuntime(build_default_registry(), llm=EchoLLM())
    watcher = ManifestWatcher(ManifestStore(tmp_path), runtime)
    seen = []
    # Bounded loop (iterations + zero interval) so the test terminates.
    serve(watcher, interval=0, on_change=seen.append, iterations=1)
    assert "engineer" in runtime.roster() and seen and seen[0].added == ["engineer"]
