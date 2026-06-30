"""Tier 5 — config-driven runtime + hot-reload registry.

Two pieces:

* :class:`ConfigDrivenAgent` — ONE generic agent runtime parameterized by a
  ``spawned_agents`` row. It runs a vanilla tool-use loop using the row's
  ``system_prompt``, ``model``, and ``tool_allowlist``. There is no
  specialist logic and no ``if row.slug == ...`` branch — that behavior
  belongs in the allowlist or the prompt.
* :class:`RegistryWatcher` — (un)registers ``dispatch_to_<slug>`` tools as
  agents are approved or archived, so the host never restarts. Trigger
  :meth:`refresh` from your change-detection mechanism (here: a 30s poll, or
  an explicit call right after approval) and once on startup.
"""

from __future__ import annotations

import threading
from typing import Optional

from agent_factory.config import Config
from agent_factory.llm import LLMClient
from agent_factory.models import SpawnedAgent
from agent_factory.repos import SpawnedAgentRepo
from agent_factory.tools.registry import Tool, ToolRegistry, tool_result, tool_to_def


class ConfigDrivenAgent:
    """A spawned agent. Pure config — no per-agent class."""

    def __init__(
        self,
        row: SpawnedAgent,
        tool_registry: ToolRegistry,
        llm: LLMClient,
        *,
        max_iters: int = 8,
    ) -> None:
        self._row = row
        self._tools = tool_registry
        self._llm = llm
        self._max_iters = max_iters

    def _filtered_tools(self) -> list[Tool]:
        allow = set(self._row.tool_allowlist)
        return [t for t in self._tools.list_all() if t.name in allow]

    def run(self, user_message: str) -> str:
        tool_defs = [tool_to_def(t) for t in self._filtered_tools()]
        messages: list[dict] = [{"role": "user", "content": user_message}]
        last_text = ""

        for _ in range(self._max_iters):
            resp = self._llm.create(
                model=self._row.model,
                system=self._row.system_prompt,
                messages=messages,
                tools=tool_defs or None,
                max_tokens=2048,
            )
            last_text = resp.text()
            tool_uses = resp.tool_uses()
            if resp.stop_reason != "tool_use" or not tool_uses:
                return last_text

            messages.append({"role": "assistant", "content": resp.content})
            results: list[dict] = []
            for tu in tool_uses:
                tool = self._tools.get(tu["name"])
                if tool is None or tool.name not in self._row.tool_allowlist:
                    results.append(
                        tool_result(tu["id"], f"tool not available: {tu['name']}", is_error=True)
                    )
                    continue
                try:
                    out = tool.execute(tu.get("input", {}) or {})
                    results.append(tool_result(tu["id"], out if isinstance(out, str) else str(out)))
                except Exception as exc:  # noqa: BLE001 - report to the model
                    results.append(tool_result(tu["id"], f"error: {exc}", is_error=True))
            messages.append({"role": "user", "content": results})

        return last_text


def build_dispatch_tool(
    slug: str,
    *,
    agents_repo: SpawnedAgentRepo,
    tool_registry: ToolRegistry,
    llm: LLMClient,
    max_iters: int = 8,
) -> Tool:
    """A uniform dispatch tool: input is always ``{"message": "..."}``."""

    def _execute(args: dict) -> str:
        row = agents_repo.get_by_slug(slug)
        if row is None or row.status != "active":
            return f"agent '{slug}' is not available"
        agent = ConfigDrivenAgent(row, tool_registry, llm, max_iters=max_iters)
        return agent.run(str(args.get("message", "")))

    row = agents_repo.get_by_slug(slug)
    specialty = row.specialty if row else slug
    return Tool(
        name=f"dispatch_to_{slug}",
        description=f"Dispatch a task to the '{slug}' agent ({specialty}).",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        execute=_execute,
        factory_allowed=False,  # dispatch tools are not handed to spawned agents
    )


class RegistryWatcher:
    """Keeps dispatch tools in sync with the active agents in the DB."""

    def __init__(
        self,
        *,
        agents_repo: SpawnedAgentRepo,
        tool_registry: ToolRegistry,
        llm: LLMClient,
        config: Optional[Config] = None,
    ) -> None:
        self._repo = agents_repo
        self._tools = tool_registry
        self._llm = llm
        self._cfg = config or Config.load()
        self._known_slugs: set[str] = set()
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def refresh(self) -> dict:
        """Reconcile registered dispatch tools with active agent rows."""
        with self._lock:
            rows = self._repo.list_active()
            new_slugs = {r.slug for r in rows}
            added, removed = [], []
            for slug in new_slugs - self._known_slugs:
                self._tools.register(
                    build_dispatch_tool(
                        slug,
                        agents_repo=self._repo,
                        tool_registry=self._tools,
                        llm=self._llm,
                        max_iters=self._cfg.agent_max_iters,
                    ),
                    replace=True,
                )
                added.append(slug)
            for slug in self._known_slugs - new_slugs:
                self._tools.unregister(f"dispatch_to_{slug}")
                removed.append(slug)
            self._known_slugs = new_slugs
            for slug in added:
                print(f"Registered dispatch_to_{slug}")
            for slug in removed:
                print(f"Unregistered dispatch_to_{slug}")
            return {"added": added, "removed": removed, "active": sorted(new_slugs)}

    def notify(self, slug: str) -> None:
        """Hook for immediate registration right after approval."""
        self.refresh()

    def start_polling(self, interval_seconds: int = 30) -> None:
        """Begin periodic reconciliation (fallback when there's no LISTEN/NOTIFY)."""
        self.refresh()

        def _tick() -> None:
            self.refresh()
            self._timer = threading.Timer(interval_seconds, _tick)
            self._timer.daemon = True
            self._timer.start()

        self._timer = threading.Timer(interval_seconds, _tick)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
