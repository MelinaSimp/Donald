"""Demo + verification for Tier 6 (live hot-reload).

  python demo_runtime.py   # no API key needed (uses a fake LLM)

Proves agents are config-driven and reloadable at runtime:
  * adding a manifest file + firing the signal -> a dispatch_to_<name> tool
    appears and is immediately callable, no restart;
  * retiring the manifest + firing the signal -> the dispatch tool disappears.
"""

from __future__ import annotations

import json
import os
import tempfile
import types

from orchestrator import (
    AgentRuntime,
    ManifestStore,
    ManifestWatcher,
    build_default_registry,
    dispatch_tool_name,
)


# --- a fake LLM so dispatch tools are callable without an API key ------------
def _fake_llm():
    def complete(*, model, system, messages, tools, max_tokens, effort="high"):
        text = f"[{model}] handled: {messages[-1]['content']}"
        block = types.SimpleNamespace(type="text", text=text)
        return types.SimpleNamespace(content=[block], stop_reason="end_turn")

    return types.SimpleNamespace(complete=complete)


def _write_manifest(directory, name, **extra):
    record = {"name": name, "system_prompt": f"You are {name}.", **extra}
    path = os.path.join(directory, f"{name}.json")
    with open(path, "w") as fh:
        json.dump(record, fh)
    return path


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        # Start with one agent on disk.
        _write_manifest(d, "engineer", allowed_tools=["calculator"])

        registry = build_default_registry()
        runtime = AgentRuntime(registry, llm=_fake_llm())
        watcher = ManifestWatcher(ManifestStore(d), runtime)

        # Initial load.
        change = watcher.poll()
        assert change and change.added == ["engineer"], change
        assert registry.has(dispatch_tool_name("engineer"))
        print("PASS: initial sync registered dispatch_to_engineer.")

        # A second poll with no disk change is a no-op (fingerprint unchanged).
        assert watcher.poll() is None
        print("PASS: no-op poll when nothing changed.")

        # 1. Add a new agent at runtime + fire the signal.
        _write_manifest(d, "designer", allowed_tools=[])
        change = watcher.poll()
        assert change and "designer" in change.added, change
        tool_name = dispatch_tool_name("designer")
        assert registry.has(tool_name), "dispatch tool did not appear"
        assert "designer" in runtime.roster()
        print(f"PASS: hot-added agent -> {tool_name} appeared, no restart.")

        # ...and it is immediately callable (runs the live agent via fake LLM).
        out = registry.get(tool_name).handler({"task": "mock up a logo"})
        assert "handled: mock up a logo" in out, out
        print(f"PASS: {tool_name} is immediately callable -> {out!r}")

        # 2. Retire the agent (deactivate) + fire the signal.
        _write_manifest(d, "designer", active=False)
        change = watcher.poll()
        assert change and "designer" in change.removed, change
        assert not registry.has(tool_name), "dispatch tool did not disappear"
        assert "designer" not in runtime.roster()
        print(f"PASS: retired agent -> {tool_name} disappeared, no restart.")

        # 3. A bad manifest is skipped, not fatal — reload stays robust.
        _write_manifest(d, "broken", allowed_tools=["does_not_exist"])
        change = watcher.poll()
        assert change and "broken" in change.invalid, change
        assert not registry.has(dispatch_tool_name("broken"))
        assert "engineer" in runtime.roster()  # the good agent survives
        print("PASS: invalid manifest skipped; the rest of the roster is intact.")

    print("\nTier 6: agents are data. The roster changes at runtime, no redeploy.")


if __name__ == "__main__":
    main()
