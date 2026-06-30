"""Demo + verification for Tier 5 (handoffs — propose, don't chain).

  python demo_handoff.py   # no API key needed

Proves the human is the circuit-breaker:
  * a proposed handoff is surfaced as a conversational offer and PAUSES;
  * nothing dispatches to the target agent until explicit acceptance;
  * artifacts ride as references (paths/IDs/URLs), never inline blobs.
"""

from __future__ import annotations

import json

from orchestrator import (
    AgentManifest,
    AgentResult,
    CallbackHandoffApprover,
    HandoffRecommendation,
    Orchestrator,
    build_default_registry,
)
from orchestrator.handoff import parse_handoff


class _SpyAgent:
    """Stand-in target agent that records whether it was dispatched."""

    def __init__(self) -> None:
        self.runs: list[str] = []

    def run(self, task: str) -> AgentResult:
        self.runs.append(task)
        return AgentResult(agent="engineer", output="built it", iterations=1, converged=True)


def _build() -> tuple[Orchestrator, _SpyAgent]:
    orch = Orchestrator(build_default_registry())
    orch.register_agent(
        AgentManifest(
            name="spec_writer",
            description="Writes specs.",
            system_prompt="x",
            allowed_tools=["propose_handoff"],  # may hand off; engineer may not
        )
    )
    orch.register_agent(
        AgentManifest(name="engineer", description="Writes code.", system_prompt="x")
    )
    spy = _SpyAgent()
    orch._agents["engineer"] = spy  # observe dispatches to the target
    return orch, spy


def main() -> None:
    rec = HandoffRecommendation(
        source_agent="spec_writer",
        target_agent="engineer",
        reason="The spec is ready; implementation is the engineer's job.",
        task="Implement the to-do CLI per the spec.",
        artifacts={"spec": "/workspace/specs/todo.md"},  # a reference, not content
        preconditions=["confirm the spec covers persistence"],
        confidence=0.9,
    )

    # 1. Surfacing the offer must NOT dispatch anything.
    orch, spy = _build()
    offer = orch.offer(rec)
    assert "engineer" in offer and rec.task in offer and "/workspace/specs/todo.md" in offer
    assert spy.runs == [], spy.runs
    print("PASS: handoff surfaced as an offer; nothing dispatched.")
    print("---- offer ----\n" + offer + "\n---------------")

    # 2. Default review holds for the human — still nothing dispatched.
    accepted, result = orch.review_handoff(rec)  # default HoldForHuman
    assert accepted is False and result is None and spy.runs == [], spy.runs
    print("PASS: default review holds for the human; target agent not run.")

    # 3. Explicit acceptance dispatches the target exactly once, with the task.
    accepted, result = orch.review_handoff(rec, CallbackHandoffApprover(lambda r: True))
    assert accepted is True and result is not None
    assert spy.runs == [rec.task], spy.runs
    print("PASS: on explicit acceptance, target dispatched exactly once with the task.")

    # 4. Artifacts must be references. An inlined blob is rejected at parse time;
    #    a path/ID/URL is accepted. The receiving agent reads from the path.
    big = "x\n" * 1000  # multi-line inline content
    try:
        parse_handoff("spec_writer", {"target_agent": "engineer", "task": "t", "artifacts": {"spec": big}})
    except ValueError as exc:
        print(f"PASS: inline-blob artifact rejected -> {exc}")
    else:
        raise AssertionError("expected inline artifact to be rejected")

    ok = parse_handoff(
        "spec_writer",
        {
            "target_agent": "engineer",
            "task": "t",
            "artifacts": {"spec": "s3://bucket/spec.md", "ticket": "JIRA-1234"},
        },
    )
    assert ok.artifacts == {"spec": "s3://bucket/spec.md", "ticket": "JIRA-1234"}
    print("PASS: reference artifacts accepted and carried as references.")

    print("\nTier 5: agents propose the graph; the human approves every edge.")


if __name__ == "__main__":
    main()
