"""Demo + verification for Tier 3 (failure isolation).

  python demo_isolation.py   # no API key needed — all three boundaries

Proves that a failure at any boundary is contained as a value, and the process
stays up:
  * tool boundary      — a throwing tool / out-of-scope name -> error result
  * observer boundary  — a throwing hook is swallowed; good hooks still fire
  * sub-agent boundary — a sub-agent that raises -> boxed AgentResult
"""

from __future__ import annotations

from orchestrator import (
    Agent,
    AgentManifest,
    AgentResult,
    EventEmitter,
    Orchestrator,
    Tool,
    build_default_registry,
)


def _boom(_inp):
    raise RuntimeError("kaboom")


def tool_boundary() -> None:
    registry = build_default_registry()
    registry.register(
        Tool(
            name="explode",
            description="Always fails.",
            input_schema={"type": "object", "properties": {}},
            handler=_boom,
        )
    )
    agent = Agent(
        AgentManifest(name="t", system_prompt="x", allowed_tools=["explode", "calculator"]),
        registry,
    )

    # A handler that raises is boxed as an error tool_result, not propagated.
    res = agent._execute_tool_call("explode", {}, "tu_1")
    assert res["is_error"] and "kaboom" in res["content"], res
    print(f"PASS: throwing tool boxed -> {res['content']}")

    # An out-of-scope tool name (PermissionError) is boxed the same way.
    res = agent._execute_tool_call("word_count", {"text": "hi"}, "tu_2")
    assert res["is_error"] and "allowlist" in res["content"], res
    print("PASS: out-of-scope tool name boxed as error result (process alive).")


def observer_boundary() -> None:
    seen = []
    emitter = EventEmitter(
        [
            lambda e, p: (_ for _ in ()).throw(ValueError("bad hook")),  # throws
            lambda e, p: seen.append((e, p)),  # must still run
        ]
    )
    emitter.emit("ping", n=1)  # must not raise despite the first observer
    assert seen == [("ping", {"n": 1})], seen
    print("PASS: throwing observer swallowed; the good observer still fired.")


def subagent_boundary() -> None:
    orch = Orchestrator(build_default_registry())

    class _BoomAgent:
        def run(self, task):
            raise RuntimeError("agent crashed")

    orch._agents["boom"] = _BoomAgent()  # inject a failing sub-agent
    res = orch._safe_run("boom", "do a thing")
    assert isinstance(res, AgentResult)
    assert not res.converged and res.error and "agent crashed" in res.error, res
    print(f"PASS: crashing sub-agent boxed -> output={res.output!r} error={res.error!r}")


if __name__ == "__main__":
    tool_boundary()
    observer_boundary()
    subagent_boundary()
    print("\nAll Tier 3 boundaries contained their failures. Process still up.")
