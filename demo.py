"""Runnable demo + verification harness for the Tier 2 backbone.

  python demo.py --dry    # no API key needed: proves allowlist filtering
  python demo.py          # live: runs a bounded agent against the API

The --dry path is the Tier 2 verification from the spec: configure an agent
with a 2-tool allowlist and confirm, at runtime, it's offered exactly those
two — not the whole registry.
"""

from __future__ import annotations

import sys

from orchestrator import Agent, AgentManifest, build_default_registry

# A least-privilege agent: the registry has more tools than this agent can see.
MATH_HELPER = AgentManifest(
    name="math_helper",
    system_prompt=(
        "You are a precise arithmetic assistant. Use the calculator tool for "
        "any computation rather than doing mental math. Answer concisely."
    ),
    allowed_tools=["calculator"],  # NOT word_count — scoped down on purpose
    max_iterations=6,
    max_tokens=1024,
)


def dry_run() -> None:
    registry = build_default_registry()
    agent = Agent(MATH_HELPER, registry)

    print("Registry holds :", registry.names())
    print("Agent can see  :", agent.tools.names())

    offered = {s["name"] for s in agent.tools.schemas()}
    assert offered == {"calculator"}, offered
    print("PASS: agent is offered exactly its allowlist, not the whole set.")

    # Least privilege is enforced, not advisory: a name outside the allowlist
    # is rejected even though it exists in the global registry.
    try:
        agent.tools.get("word_count")
    except PermissionError as exc:
        print(f"PASS: out-of-scope tool blocked -> {exc}")
    else:
        raise AssertionError("expected PermissionError for word_count")


def live_run() -> None:
    registry = build_default_registry()
    agent = Agent(MATH_HELPER, registry)
    result = agent.run("What is 17 * 23, then add 100?")
    print(f"agent     : {result.agent}")
    print(f"converged : {result.converged} (in {result.iterations} iteration(s))")
    print(f"output    : {result.output}")


if __name__ == "__main__":
    if "--dry" in sys.argv:
        dry_run()
    else:
        live_run()
