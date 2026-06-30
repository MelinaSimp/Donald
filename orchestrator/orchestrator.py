"""The orchestrator — Tier 1's smart router (dispatch intelligence).

The conductor decides *who* does what and *whether* to ask first, then gets out
of the way. It is a router, not a worker: no domain logic lives here. The four
routing rules it enforces on every request:

  1. Ownership      — dispatch each piece of work to the agent that owns it.
  2. Ordering       — a design/spec step precedes an implementation step.
  3. Decomposition  — a multi-step request becomes an ordered list of separate
                      dispatches, not one blurred mega-dispatch.
  4. Clarify, don't guess — if a request is genuinely ambiguous between two
                      agents, ask ONE short question instead of guessing.

Key design decision: routing intelligence belongs to the orchestrator alone.
Individual agents never learn about each other — that knowledge centralizes in
the conductor's routing policy, which it builds from the agent roster.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .agent import Agent, AgentManifest, AgentResult
from .confirmation import Approver
from .events import EventEmitter, Observer
from .handoff import (
    HandoffApprover,
    HandoffRecommendation,
    HoldForHuman,
    format_offer,
)
from .llm import LLM, DEFAULT_MODEL
from .registry import ToolRegistry
from .runtime import ChangeSet

logger = logging.getLogger(__name__)

# The router is constrained to this shape so the conductor reads a decision,
# never free-form prose. `question` is "" unless kind == "clarify".
ROUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "kind": {"type": "string", "enum": ["dispatch", "clarify"]},
        "question": {"type": "string"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "task": {"type": "string"},
                },
                "required": ["agent", "task"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reasoning", "kind", "question", "plan"],
    "additionalProperties": False,
}


@dataclass
class RouteStep:
    agent: str
    task: str


@dataclass
class RoutingDecision:
    kind: str  # "dispatch" | "clarify"
    reasoning: str
    question: str = ""
    plan: list[RouteStep] = field(default_factory=list)


class Orchestrator:
    """Holds the agent roster and routes requests across it."""

    def __init__(
        self,
        registry: ToolRegistry,
        llm: LLM | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 2048,
        observers: list[Observer] | None = None,
        approver: Approver | None = None,
    ) -> None:
        self._registry = registry
        self._model = model
        self._max_tokens = max_tokens
        self._manifests: dict[str, AgentManifest] = {}
        self._agents: dict[str, Agent] = {}
        self._llm = llm
        self._events = EventEmitter(observers)
        # One confirmation gate shared by every agent the conductor dispatches.
        self._approver = approver

    def _ensure_llm(self) -> LLM:
        if self._llm is None:
            self._llm = LLM()
        return self._llm

    def subscribe(self, observer: Observer) -> None:
        """Register a fire-and-forget observer (UI, logs, analytics)."""
        self._events.subscribe(observer)

    def register_agent(self, manifest: AgentManifest) -> None:
        if manifest.name in self._manifests:
            raise ValueError(f"agent already registered: {manifest.name!r}")
        # Build the Agent now so an invalid allowlist fails at registration.
        # Agents share the orchestrator's event bus so tool-level events surface.
        self._agents[manifest.name] = Agent(
            manifest, self._registry, self._llm, self._events, self._approver
        )
        self._manifests[manifest.name] = manifest

    def sync(self, manifests: dict[str, AgentManifest]) -> ChangeSet:
        """Reconcile the live roster against a desired manifest set (Tier 6).

        This is what makes the conductor hot-reloadable: routing (Tier 1) is
        built from `_manifests`, so once a manifest is added or retired here,
        the router covers — or stops covering — that agent on the next turn.
        Dispatch still flows through the conductor, never agent-to-agent, so
        Tier 5's "no silent chaining" rule is preserved.

        A bad manifest is skipped (not fatal), matching the runtime's behavior.
        """
        change = ChangeSet()
        for name in list(self._manifests):
            if name not in manifests:
                self._drop_agent(name)
                change.removed.append(name)
        for name, manifest in manifests.items():
            if name not in self._manifests:
                (change.added if self._add_agent(name, manifest) else change.invalid).append(name)
            elif self._manifests[name] != manifest:
                self._drop_agent(name)
                (change.updated if self._add_agent(name, manifest) else change.invalid).append(name)
        if not change.is_empty():
            logger.info(
                "conductor roster: +%s -%s ~%s !%s",
                change.added, change.removed, change.updated, change.invalid,
            )
        return change

    def _add_agent(self, name: str, manifest: AgentManifest) -> bool:
        try:
            agent = Agent(
                manifest, self._registry, self._llm, self._events, self._approver
            )
        except Exception as exc:  # noqa: BLE001 — a bad manifest must not kill reload
            logger.warning("conductor skipping invalid manifest %r: %s", name, exc)
            self._events.emit("agent.invalid", agent=name, error=str(exc))
            return False
        self._agents[name] = agent
        self._manifests[name] = manifest
        self._events.emit("agent.registered", agent=name)
        return True

    def _drop_agent(self, name: str) -> None:
        self._agents.pop(name, None)
        self._manifests.pop(name, None)
        self._events.emit("agent.unregistered", agent=name)

    def roster(self) -> list[str]:
        return sorted(self._manifests)

    def routing_policy(self) -> str:
        """The system prompt the router reads on every turn.

        Built from the roster, so adding an agent automatically teaches the
        conductor about it — and no agent has to know about the others.
        """
        if not self._manifests:
            agent_lines = "  (no agents registered)"
        else:
            agent_lines = "\n".join(
                f"  - {m.name}: {m.description or m.system_prompt[:80]}"
                for m in sorted(self._manifests.values(), key=lambda m: m.name)
            )
        return (
            "You are the orchestrator — the conductor for a team of specialist "
            "agents. Your ONLY job is to route work; you never do the work "
            "yourself.\n\n"
            "Agents you can dispatch to:\n"
            f"{agent_lines}\n\n"
            "Routing rules:\n"
            "  1. Ownership: dispatch each piece of work to the agent that owns "
            "it (listed above). Use only those exact agent names.\n"
            "  2. Ordering: when a request needs both a design/spec step and an "
            "implementation step, the design/spec step MUST come first.\n"
            "  3. Decomposition: a multi-step request becomes multiple ordered "
            "steps in `plan` — one agent action each — not one blurred dispatch.\n"
            "  4. Clarify, don't guess: if the request is genuinely ambiguous "
            "between two agents, set kind=\"clarify\" and ask ONE short "
            "question. Leave `plan` empty in that case.\n\n"
            "When dispatching, set kind=\"dispatch\" and fill `plan` with the "
            "ordered steps; leave `question` empty."
        )

    def route(self, request: str) -> RoutingDecision:
        """Decide how to handle a request — dispatch plan or one question."""
        llm = self._ensure_llm()
        response = llm.decide(
            model=self._model,
            system=self.routing_policy(),
            messages=[{"role": "user", "content": request}],
            schema=ROUTING_SCHEMA,
            max_tokens=self._max_tokens,
        )
        data = _first_json(response)
        decision = RoutingDecision(
            kind=data["kind"],
            reasoning=data.get("reasoning", ""),
            question=data.get("question", ""),
            plan=[RouteStep(agent=s["agent"], task=s["task"]) for s in data.get("plan", [])],
        )
        # Guard: the model may only route to agents that actually exist.
        unknown = [s.agent for s in decision.plan if s.agent not in self._agents]
        if unknown:
            raise ValueError(f"router chose unknown agent(s): {unknown}")
        self._events.emit(
            "route.decided",
            kind=decision.kind,
            plan=[s.agent for s in decision.plan],
            question=decision.question,
        )
        return decision

    def dispatch(self, request: str) -> tuple[RoutingDecision, list[AgentResult]]:
        """Route, then execute the dispatch plan in order.

        On a clarify decision, nothing is dispatched — the caller surfaces the
        question to the human and re-submits with the answer.
        """
        decision = self.route(request)
        if decision.kind == "clarify":
            return decision, []
        results = [self._safe_run(step.agent, step.task) for step in decision.plan]
        return decision, results

    def _safe_run(self, name: str, task: str) -> AgentResult:
        """Run a sub-agent, boxing any failure so the conductor stays alive.

        A Tier 3 boundary: if the agent's run raises (API error, bug, anything),
        the orchestrator gets a human-friendly result plus a short error string
        for logs — never an exception that kills the whole dispatch.
        """
        self._events.emit("dispatch.start", agent=name, task=task)
        try:
            result = self._agents[name].run(task)
        except Exception as exc:  # noqa: BLE001 — box the failure as data
            logger.warning("sub-agent %r failed: %s", name, exc)
            self._events.emit("dispatch.error", agent=name, error=str(exc))
            return AgentResult(
                agent=name,
                output=f"[the {name} agent ran into trouble and was skipped]",
                iterations=0,
                converged=False,
                stop_reason="error",
                error=f"{type(exc).__name__}: {exc}",
            )
        self._events.emit("dispatch.done", agent=name, converged=result.converged)
        return result

    # --- Tier 5: handoffs (propose, don't chain) -----------------------

    def offer(self, recommendation: HandoffRecommendation) -> str:
        """Render a proposed handoff as a conversational offer. No side effects.

        This only *surfaces* the proposal — it never dispatches. The caller
        shows this to the human and waits.
        """
        self._events.emit("handoff.offered", target=recommendation.target_agent)
        return format_offer(recommendation)

    def accept_handoff(self, recommendation: HandoffRecommendation) -> AgentResult:
        """Dispatch a handoff the human has approved — the only path that runs it."""
        if recommendation.target_agent not in self._agents:
            raise ValueError(
                f"handoff target is not a registered agent: {recommendation.target_agent!r}"
            )
        self._events.emit("handoff.accepted", target=recommendation.target_agent)
        return self._safe_run(recommendation.target_agent, recommendation.task)

    def review_handoff(
        self,
        recommendation: HandoffRecommendation,
        approver: HandoffApprover | None = None,
    ) -> tuple[bool, AgentResult | None]:
        """Surface the offer, then dispatch ONLY if the approver says yes.

        The default approver is `HoldForHuman` — it never accepts, so nothing
        is dispatched until a human explicitly approves the edge. Pass a
        `CallbackHandoffApprover` to wire in a UI decision or automate a test.
        """
        approver = approver or HoldForHuman()
        self.offer(recommendation)
        if approver.decide(recommendation):
            return True, self.accept_handoff(recommendation)
        self._events.emit("handoff.declined", target=recommendation.target_agent)
        return False, None


def _first_json(response) -> dict:
    """Parse the first text block of a structured-output response as JSON."""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise ValueError("routing response contained no text block")
