"""End-to-end demo: a hot-reloadable conductor (Tier 1 routing + Tier 6 reload).

  python demo_live_roster.py   # no API key needed (scripted routing LLM)

The orchestrator routes over the live roster maintained from the manifest
store. Add an agent on disk and the conductor starts routing to it; retire it
and the conductor stops — no restart. Dispatch always flows through the
conductor, never agent-to-agent (Tier 5 preserved).
"""

from __future__ import annotations

import json
import os
import tempfile
import types

from orchestrator import ManifestStore, ManifestWatcher, Orchestrator, build_default_registry


class _RoutingLLM:
    """Scriptable stand-in: `decide` returns a routing plan; `complete` runs an agent."""

    def __init__(self) -> None:
        self.target = "engineer"

    def decide(self, **_kwargs):
        data = {
            "reasoning": "scripted",
            "kind": "dispatch",
            "question": "",
            "plan": [{"agent": self.target, "task": f"work for {self.target}"}],
        }
        block = types.SimpleNamespace(type="text", text=json.dumps(data))
        return types.SimpleNamespace(content=[block], stop_reason="end_turn")

    def complete(self, *, model, messages, **_kwargs):
        block = types.SimpleNamespace(type="text", text=f"[{model}] did: {messages[-1]['content']}")
        return types.SimpleNamespace(content=[block], stop_reason="end_turn")


def _write(directory, name, **extra):
    path = os.path.join(directory, f"{name}.json")
    with open(path, "w") as fh:
        json.dump({"name": name, "system_prompt": f"You are {name}.", **extra}, fh)


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        _write(d, "engineer", description="Writes code.", allowed_tools=["calculator"])

        llm = _RoutingLLM()
        conductor = Orchestrator(build_default_registry(), llm=llm)
        watcher = ManifestWatcher(ManifestStore(d), conductor)  # drives the conductor

        watcher.poll()
        assert conductor.roster() == ["engineer"]
        print("PASS: conductor loaded its roster from disk -> ['engineer']")

        # Route + dispatch to the only agent.
        llm.target = "engineer"
        decision, results = conductor.dispatch("build a thing")
        assert results and results[0].agent == "engineer"
        print(f"PASS: routed to engineer -> {results[0].output!r}")

        # 1. Hot-add a 'designer' agent on disk + fire the signal.
        _write(d, "designer", description="Designs UIs.", allowed_tools=[])
        change = watcher.poll()
        assert "designer" in change.added and "designer" in conductor.roster()
        assert "designer" in conductor.routing_policy()
        print("PASS: hot-added 'designer' -> now in the roster and routing policy.")

        # The conductor can immediately route to the new agent — no restart.
        llm.target = "designer"
        decision, results = conductor.dispatch("design a screen")
        assert results and results[0].agent == "designer"
        print(f"PASS: conductor routed to the hot-added agent -> {results[0].output!r}")

        # 2. Retire 'designer' + fire the signal.
        _write(d, "designer", active=False)
        change = watcher.poll()
        assert "designer" in change.removed and "designer" not in conductor.roster()

        # The conductor now refuses to route to the retired agent (guard fires).
        llm.target = "designer"
        try:
            conductor.route("design another screen")
        except ValueError as exc:
            print(f"PASS: conductor stopped routing to the retired agent -> {exc}")
        else:
            raise AssertionError("expected routing to retired agent to fail")

    print("\nEnd-to-end: routing follows the live, hot-reloaded roster — no restart.")


if __name__ == "__main__":
    main()
