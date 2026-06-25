"""The generic, config-driven agent — Tier 2's bounded worker.

There is no bespoke class per agent: a *manifest* (system prompt, model, tool
allowlist, bounds) fully describes an agent, and one `Agent` class runs the
standard bounded tool-use loop for any of them. This is what Tier 6 will
hot-reload from disk — the manifest *is* the agent.

What this tier guarantees:
  * Least privilege  — the agent only ever sees the tools in its allowlist.
  * Bounded loops    — MAX_ITERATIONS caps the tool-use loop; on exhaustion it
                       returns a clean "didn't converge", never a hang.
  * Bounded calls    — max_tokens ceiling and a declared model per agent.

Tier 3 adds failure isolation at the tool-execution boundary: a tool that
raises is converted to an error tool_result the model can read and react to,
never an exception that escapes the loop. The confirmation gate (Tier 4) is
still deliberately out of scope.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .confirmation import Approver, ConfirmationDecision, ConfirmationRequest, DenyAll
from .events import EventEmitter
from .llm import LLM, DEFAULT_MODEL
from .registry import ToolRegistry, ToolView

logger = logging.getLogger(__name__)


@dataclass
class AgentManifest:
    """Everything needed to instantiate an agent — data, not code."""

    name: str
    system_prompt: str
    # A one-line statement of what this agent owns, read by the Tier 1 router.
    # Note: this describes the agent to the *orchestrator*; the agent's own
    # system_prompt never mentions other agents (they stay ignorant of each
    # other — routing knowledge centralizes in the conductor).
    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    max_iterations: int = 8
    max_tokens: int = 4096
    effort: str = "high"


@dataclass
class AgentResult:
    agent: str
    output: str
    iterations: int
    converged: bool
    stop_reason: str | None = None
    error: str | None = None  # short log string when a boundary boxed a failure


class Agent:
    """A manifest bound to a registry view and an LLM."""

    def __init__(
        self,
        manifest: AgentManifest,
        registry: ToolRegistry,
        llm: LLM | None = None,
        events: EventEmitter | None = None,
        approver: Approver | None = None,
    ) -> None:
        self.manifest = manifest
        # Resolve the allowlist into a filtered view now, so an invalid
        # manifest fails at construction rather than mid-run.
        self.tools: ToolView = registry.view(manifest.allowed_tools)
        # LLM is created lazily on first run so dry inspection (and tests)
        # don't require an API key.
        self._llm = llm
        self._events = events or EventEmitter()
        # Fail-safe default: gated tools don't run without an explicit approver.
        self._approver = approver or DenyAll()

    def _ensure_llm(self) -> LLM:
        if self._llm is None:
            self._llm = LLM()
        return self._llm

    def run(self, task: str) -> AgentResult:
        m = self.manifest
        llm = self._ensure_llm()
        tool_schemas = self.tools.schemas()
        messages: list[dict] = [{"role": "user", "content": task}]
        last_stop: str | None = None

        for i in range(1, m.max_iterations + 1):
            response = llm.complete(
                model=m.model,
                system=m.system_prompt,
                messages=messages,
                tools=tool_schemas,
                max_tokens=m.max_tokens,
                effort=m.effort,
            )
            last_stop = response.stop_reason
            # Echo the full assistant turn back — including thinking blocks,
            # which the API requires to be preserved verbatim across turns.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return AgentResult(
                    agent=m.name,
                    output=_text_of(response),
                    iterations=i,
                    converged=True,
                    stop_reason=last_stop,
                )

            # Execute each requested tool and feed all results back in a single
            # user turn (the API expects one tool_result per tool_use, batched).
            tool_results = [
                self._execute_tool_call(block.name, dict(block.input), block.id)
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})

        # Loop exhausted without the model finishing — bounded, not hung.
        return AgentResult(
            agent=m.name,
            output=f"[did not converge within {m.max_iterations} iterations]",
            iterations=m.max_iterations,
            converged=False,
            stop_reason=last_stop,
        )

    def _execute_tool_call(
        self, name: str, tool_input: dict[str, Any], tool_use_id: str
    ) -> dict[str, Any]:
        """Route one tool call: gate it (Tier 4), then run it (Tier 3 boxed).

        Two boundaries meet here, both owned by the router rather than the tool:
          * Tier 4 — if the tool requires confirmation, surface the request to
            the approver and DON'T execute unless explicitly approved.
          * Tier 3 — an out-of-scope name (PermissionError) or a throwing
            handler becomes a structured error result, never an exception.
        """
        self._events.emit("tool.start", agent=self.manifest.name, tool=name)
        try:
            tool = self.tools.get(name)  # enforces the allowlist
            if tool.requires_confirmation:
                decision = self._gate(name, tool_input)
                if not decision.approved:
                    self._events.emit(
                        "confirmation.denied",
                        agent=self.manifest.name,
                        tool=name,
                        reason=decision.reason,
                    )
                    return _tool_result(
                        tool_use_id,
                        json.dumps(
                            {
                                "confirmation_required": True,
                                "tool": name,
                                "input": tool_input,
                                "status": "not_executed",
                                "reason": decision.reason,
                            }
                        ),
                        is_error=False,  # not an error — the model should adapt
                    )
                self._events.emit(
                    "confirmation.approved", agent=self.manifest.name, tool=name
                )
            # Execute-confirmed (or ungated) path — the only place a handler runs.
            content = self._invoke_handler(tool, tool_input)
        except Exception as exc:  # noqa: BLE001 — box the failure as data
            logger.warning(
                "tool %r failed in agent %r: %s", name, self.manifest.name, exc
            )
            self._events.emit(
                "tool.error", agent=self.manifest.name, tool=name, error=str(exc)
            )
            return _tool_result(
                tool_use_id,
                json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                is_error=True,
            )
        self._events.emit("tool.result", agent=self.manifest.name, tool=name)
        return _tool_result(tool_use_id, content, is_error=False)

    def _gate(self, name: str, tool_input: dict[str, Any]) -> ConfirmationDecision:
        """Surface a confirmation request to the approver and return its verdict."""
        request = ConfirmationRequest(
            agent=self.manifest.name, tool=name, tool_input=tool_input
        )
        self._events.emit(
            "confirmation.required",
            agent=self.manifest.name,
            tool=name,
            input=tool_input,
        )
        return self._approver.decide(request)

    def _invoke_handler(self, tool, tool_input: dict[str, Any]) -> str:
        """Run the tool handler — the execute path, with no gate. Internal."""
        return tool.handler(tool_input)

    def execute_confirmed(self, name: str, tool_input: dict[str, Any]) -> str:
        """Run a gated tool AFTER out-of-band human approval — bypasses the gate.

        Still enforces the allowlist (least privilege). This is the separate
        "execute-confirmed" path: callers approve a `ConfirmationRequest`, then
        invoke this to actually perform the action.
        """
        return self._invoke_handler(self.tools.get(name), tool_input)


def _tool_result(tool_use_id: str, content: str, *, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }


def _text_of(response) -> str:
    """Concatenate the text blocks of a response into a plain string."""
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()
