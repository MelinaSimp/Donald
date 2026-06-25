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
from dataclasses import dataclass, field

from .agent import Agent, AgentManifest, AgentResult
from .llm import LLM, DEFAULT_MODEL
from .registry import ToolRegistry

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
    ) -> None:
        self._registry = registry
        self._model = model
        self._max_tokens = max_tokens
        self._manifests: dict[str, AgentManifest] = {}
        self._agents: dict[str, Agent] = {}
        self._llm = llm

    def _ensure_llm(self) -> LLM:
        if self._llm is None:
            self._llm = LLM()
        return self._llm

    def register_agent(self, manifest: AgentManifest) -> None:
        if manifest.name in self._manifests:
            raise ValueError(f"agent already registered: {manifest.name!r}")
        # Build the Agent now so an invalid allowlist fails at registration.
        self._agents[manifest.name] = Agent(manifest, self._registry, self._llm)
        self._manifests[manifest.name] = manifest

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
        return decision

    def dispatch(self, request: str) -> tuple[RoutingDecision, list[AgentResult]]:
        """Route, then execute the dispatch plan in order.

        On a clarify decision, nothing is dispatched — the caller surfaces the
        question to the human and re-submits with the answer.
        """
        decision = self.route(request)
        if decision.kind == "clarify":
            return decision, []
        results = [self._agents[step.agent].run(step.task) for step in decision.plan]
        return decision, results


def _first_json(response) -> dict:
    """Parse the first text block of a structured-output response as JSON."""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise ValueError("routing response contained no text block")
