"""Live hot-reload — Tier 6. Agents as data, reloadable at runtime.

Agents are manifests (data), not classes, so the *set* of available agents can
change while the process runs. This module is the config-driven runtime:

  * ManifestStore   — flat JSON files on disk are the source of truth for which
                      agents exist right now.
  * AgentRuntime    — keeps a live roster in sync with a set of manifests, and
                      maintains a `dispatch_to_<name>` tool per agent.
  * ManifestWatcher — on a change signal (here: a directory poll) reloads the
                      store and applies the diff: new agents register, retired
                      ones unregister. No restart, no redeploy.

Key design decision: the *capability* (a `dispatch_to_<name>` tool) and the
*agent definition* (a manifest) are decoupled. The watcher's only job is to
keep the live set of dispatch tools in sync with the manifest store. Adding an
agent = dropping a manifest file + firing the signal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .agent import Agent, AgentManifest
from .confirmation import Approver
from .events import EventEmitter
from .llm import LLM, DEFAULT_MODEL
from .registry import Tool, ToolRegistry

logger = logging.getLogger(__name__)


def dispatch_tool_name(agent_name: str) -> str:
    return f"dispatch_to_{agent_name}"


def manifest_from_dict(data: dict[str, Any]) -> AgentManifest:
    """Build a manifest from a flat-file record (the on-disk schema)."""
    return AgentManifest(
        name=data["name"],
        system_prompt=data.get("system_prompt", ""),
        description=data.get("description", ""),
        allowed_tools=list(data.get("allowed_tools", [])),
        model=data.get("model", DEFAULT_MODEL),
        max_iterations=int(data.get("max_iterations", 8)),
        max_tokens=int(data.get("max_tokens", 4096)),
        effort=data.get("effort", "high"),
    )


@dataclass
class ChangeSet:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.updated or self.invalid)


class AgentRuntime:
    """Holds the live roster and keeps dispatch tools in sync with manifests."""

    def __init__(
        self,
        registry: ToolRegistry,
        llm: LLM | None = None,
        events: EventEmitter | None = None,
        approver: Approver | None = None,
    ) -> None:
        self._registry = registry
        self._llm = llm
        self._events = events or EventEmitter()
        self._approver = approver
        self._agents: dict[str, Agent] = {}
        self._manifests: dict[str, AgentManifest] = {}

    def roster(self) -> list[str]:
        return sorted(self._agents)

    def dispatch_tools(self) -> list[str]:
        return sorted(
            n for n in (dispatch_tool_name(a) for a in self._agents)
            if self._registry.has(n)
        )

    def get_agent(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def sync(self, manifests: dict[str, AgentManifest]) -> ChangeSet:
        """Diff the desired manifest set against the live roster and apply it."""
        change = ChangeSet()

        # Retire agents whose manifest is gone.
        for name in list(self._manifests):
            if name not in manifests:
                self._drop(name)
                change.removed.append(name)

        # Add new agents; rebuild changed ones.
        for name, manifest in manifests.items():
            if name not in self._manifests:
                if self._add(name, manifest):
                    change.added.append(name)
                else:
                    change.invalid.append(name)
            elif self._manifests[name] != manifest:
                self._drop(name)
                if self._add(name, manifest):
                    change.updated.append(name)
                else:
                    change.invalid.append(name)

        if not change.is_empty():
            logger.info(
                "hot-reload: +%s -%s ~%s !%s",
                change.added, change.removed, change.updated, change.invalid,
            )
        return change

    def _add(self, name: str, manifest: AgentManifest) -> bool:
        """Register one agent + its dispatch tool. Returns False on a bad manifest."""
        try:
            agent = Agent(
                manifest, self._registry, self._llm, self._events, self._approver
            )
        except Exception as exc:  # noqa: BLE001 — a bad manifest must not kill reload
            logger.warning("skipping invalid manifest %r: %s", name, exc)
            self._events.emit("agent.invalid", agent=name, error=str(exc))
            return False
        self._agents[name] = agent
        self._manifests[name] = manifest
        self._registry.upsert(self._make_dispatch_tool(name))
        self._events.emit("agent.registered", agent=name)
        return True

    def _drop(self, name: str) -> None:
        self._agents.pop(name, None)
        self._manifests.pop(name, None)
        self._registry.unregister(dispatch_tool_name(name))
        self._events.emit("agent.unregistered", agent=name)

    def _make_dispatch_tool(self, name: str) -> Tool:
        """Factory: a `dispatch_to_<name>` tool wired to the live runtime.

        It resolves the agent at call time, so a tool registered now keeps
        pointing at the current manifest even after a reload swaps it out.
        """

        def handler(inp: dict[str, Any]) -> str:
            agent = self.get_agent(name)
            if agent is None:
                return json.dumps({"error": f"agent {name!r} is no longer registered"})
            return agent.run(str(inp.get("task", ""))).output

        return Tool(
            name=dispatch_tool_name(name),
            description=f"Dispatch a natural-language task to the {name} agent.",
            input_schema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for the agent."}
                },
                "required": ["task"],
            },
            handler=handler,
        )


class ManifestStore:
    """Flat-file manifest store: one JSON file per agent in a directory.

    A file present (and not `"active": false`) means the agent exists; removing
    the file or setting `active=false` retires it.
    """

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)

    def load(self) -> dict[str, AgentManifest]:
        manifests: dict[str, AgentManifest] = {}
        if not self.dir.is_dir():
            return manifests
        for path in sorted(self.dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("skipping unreadable manifest %s: %s", path.name, exc)
                continue
            if not data.get("active", True):
                continue
            manifest = manifest_from_dict(data)
            manifests[manifest.name] = manifest
        return manifests

    def fingerprint(self) -> tuple:
        """A cheap change signal: filenames + modification times."""
        if not self.dir.is_dir():
            return ()
        return tuple(
            sorted((p.name, p.stat().st_mtime_ns) for p in self.dir.glob("*.json"))
        )


@runtime_checkable
class Syncable(Protocol):
    """Anything whose roster can be reconciled to a manifest set.

    Both `AgentRuntime` (which also maintains dispatch tools) and `Orchestrator`
    (which routes over the roster) satisfy this, so a watcher can drive either.
    """

    def sync(self, manifests: dict[str, AgentManifest]) -> "ChangeSet": ...


class ManifestWatcher:
    """Drives hot-reload: when the store changes, sync the target.

    `poll()` is the change signal. Call it on a file-watch event (inotify /
    `watchdog`) or on an interval; it reloads and applies a diff only when the
    directory's fingerprint actually changed. The target is anything `Syncable`
    — an `AgentRuntime` or an `Orchestrator`.
    """

    def __init__(self, store: ManifestStore, target: Syncable) -> None:
        self._store = store
        self._target = target
        self._fingerprint: tuple | None = None

    @property
    def store(self) -> ManifestStore:
        return self._store

    def poll(self) -> ChangeSet | None:
        """Return the applied ChangeSet if the store changed, else None."""
        fingerprint = self._store.fingerprint()
        if fingerprint == self._fingerprint:
            return None
        self._fingerprint = fingerprint
        return self._target.sync(self._store.load())
