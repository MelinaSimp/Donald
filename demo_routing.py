"""Demo + verification for Tier 1 (smart routing).

  python demo_routing.py --dry   # no API key: policy + agent-isolation checks
  python demo_routing.py         # live: routes the four spec scenarios

Live verification (from the spec):
  * one request obviously for agent A, one obviously for B  -> routed correctly
  * one genuinely ambiguous between them                    -> asks ONE question
  * a multi-step request -> an ordered plan of separate dispatches, not one blur
"""

from __future__ import annotations

import sys

from orchestrator import AgentManifest, Orchestrator, build_default_registry

# Three specialists with a natural sequence between two of them (spec -> code).
# Note: none of these system prompts mention the others — agents stay ignorant
# of each other; only the orchestrator knows the roster.
SPEC_WRITER = AgentManifest(
    name="spec_writer",
    description="Turns vague feature ideas into a short written spec/plan BEFORE any code is written.",
    system_prompt=(
        "You are a product spec writer. Given a feature idea, produce a short, "
        "concrete written specification: goals, key behaviors, and constraints. "
        "Do not write code."
    ),
)
ENGINEER = AgentManifest(
    name="engineer",
    description="Writes and edits code to implement an existing spec or a concrete coding request.",
    system_prompt=(
        "You are a software engineer. Implement what is asked as clean, working "
        "code with a brief explanation."
    ),
)
MATH_HELPER = AgentManifest(
    name="math_helper",
    description="Performs arithmetic and numeric calculations.",
    system_prompt=(
        "You are a precise arithmetic assistant. Use the calculator tool for "
        "any computation rather than doing mental math. Answer concisely."
    ),
    allowed_tools=["calculator"],
    max_tokens=1024,
)

ROSTER = [SPEC_WRITER, ENGINEER, MATH_HELPER]

SCENARIOS = {
    "obvious -> math_helper": "What is 19 * 47?",
    "obvious -> engineer": "Write a Python function that reverses a linked list.",
    "ambiguous (spec vs engineer)": "Build me a dashboard.",
    "multi-step (spec then engineer)": "Design and build a command-line to-do app.",
}


def _build() -> Orchestrator:
    orch = Orchestrator(build_default_registry())
    for m in ROSTER:
        orch.register_agent(m)
    return orch


def dry_run() -> None:
    orch = _build()
    print("Roster:", orch.roster())
    print("\n--- routing policy the conductor reads ---")
    print(orch.routing_policy())

    # Invariant: every agent appears in the policy (roster-built, not hardcoded).
    policy = orch.routing_policy()
    for m in ROSTER:
        assert m.name in policy, m.name
    print("\nPASS: policy is built from the roster (all agents present).")

    # Invariant: agents stay ignorant of each other — no agent's own system
    # prompt names another agent. Routing knowledge lives only in the conductor.
    for m in ROSTER:
        others = [o.name for o in ROSTER if o is not m]
        leaked = [name for name in others if name in m.system_prompt]
        assert not leaked, f"{m.name} leaks {leaked}"
    print("PASS: no agent's system prompt references another agent.")


def live_run() -> None:
    orch = _build()
    for label, request in SCENARIOS.items():
        decision = orch.route(request)
        print(f"\n[{label}]\n  request : {request}")
        if decision.kind == "clarify":
            print(f"  -> CLARIFY: {decision.question}")
        else:
            steps = " -> ".join(f"{s.agent}({s.task[:40]}...)" for s in decision.plan)
            print(f"  -> DISPATCH: {steps}")


if __name__ == "__main__":
    if "--dry" in sys.argv:
        dry_run()
    else:
        live_run()
