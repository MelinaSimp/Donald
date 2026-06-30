"""The handoff system — Tier 5. Propose, don't chain.

When an agent finishes, it can *recommend* the next step and which agent should
take it — but it never dispatches that agent itself. The recommendation is a
small, typed object carrying references (not blobs); the orchestrator surfaces
it as a conversational offer and waits. The human is the circuit-breaker that
approves each edge of the work graph.

The recommendation rides on a control tool, `propose_handoff`, which the agent
loop intercepts (it is never executed as a side effect). Whether an agent may
hand off at all is therefore governed by the same allowlist mechanism as any
other tool (Tier 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from .registry import Tool

HANDOFF_TOOL_NAME = "propose_handoff"

# Artifacts must be references (paths/IDs/URLs), not inline content — that keeps
# a handoff small, serializable, and cheap to log. Anything longer than this, or
# containing newlines, is treated as an inlined blob and rejected.
MAX_REF_LEN = 512


@dataclass
class HandoffRecommendation:
    source_agent: str
    target_agent: str
    reason: str
    task: str
    artifacts: dict[str, str] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    confidence: float = 0.5


HANDOFF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target_agent": {
            "type": "string",
            "description": "Which agent should take the next step.",
        },
        "reason": {
            "type": "string",
            "description": "One human-readable sentence on why to hand off.",
        },
        "task": {
            "type": "string",
            "description": "The task to pass the next agent verbatim if accepted.",
        },
        "artifacts": {
            "type": "object",
            "description": (
                "Map of name -> path/ID/URL the next agent should read. "
                "References ONLY — never inline file contents or large blobs."
            ),
            "additionalProperties": {"type": "string"},
        },
        "preconditions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things the human should verify before accepting.",
        },
        "confidence": {
            "type": "number",
            "description": "0..1 — how strongly you vouch for this handoff.",
        },
    },
    "required": ["target_agent", "reason", "task"],
}


def make_handoff_tool() -> Tool:
    """Build the `propose_handoff` control tool for registration.

    Its handler is never called — the agent loop intercepts the tool by name
    and records the proposal instead of executing anything. The defensive
    handler exists only so a misrouted call fails loudly rather than silently.
    """

    def _never(_inp: dict[str, Any]) -> str:  # pragma: no cover - defensive
        raise RuntimeError("propose_handoff is a control tool; it is intercepted, not run")

    return Tool(
        name=HANDOFF_TOOL_NAME,
        description=(
            "Recommend the next step and which agent should take it. This does "
            "NOT dispatch that agent — a human reviews and decides. Pass "
            "artifacts as references (paths/IDs/URLs), never inline content."
        ),
        input_schema=HANDOFF_SCHEMA,
        handler=_never,
    )


def parse_handoff(source_agent: str, data: dict[str, Any]) -> HandoffRecommendation:
    """Validate and normalize a raw handoff proposal from an agent.

    Rejects artifact values that look like inlined content rather than
    references — a handoff must stay small and serializable.
    """
    target = str(data.get("target_agent", "")).strip()
    task = str(data.get("task", "")).strip()
    if not target or not task:
        raise ValueError("target_agent and task are required")

    raw_artifacts = data.get("artifacts") or {}
    if not isinstance(raw_artifacts, dict):
        raise ValueError("artifacts must be a map of name -> reference")
    artifacts: dict[str, str] = {}
    for key, value in raw_artifacts.items():
        ref = str(value)
        if "\n" in ref or len(ref) > MAX_REF_LEN:
            raise ValueError(
                f"artifact {key!r} looks like inline content; pass a path/ID/URL "
                "reference instead"
            )
        artifacts[str(key)] = ref

    preconditions = [str(x) for x in (data.get("preconditions") or [])]
    confidence = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
    return HandoffRecommendation(
        source_agent=source_agent,
        target_agent=target,
        reason=str(data.get("reason", "")).strip(),
        task=task,
        artifacts=artifacts,
        preconditions=preconditions,
        confidence=confidence,
    )


def format_offer(rec: HandoffRecommendation) -> str:
    """Render a handoff as a conversational offer, phrased by confidence."""
    if rec.confidence >= 0.8:
        lead = "Definitely worth handing off"
    elif rec.confidence >= 0.5:
        lead = "You might want to hand off"
    else:
        lead = "Low-confidence suggestion to hand off"

    lines = [
        f"{lead} to {rec.target_agent!r} (confidence {rec.confidence:.2f}).",
        f"  why : {rec.reason}",
        f"  task: {rec.task}",
    ]
    if rec.artifacts:
        lines.append("  artifacts (references the next agent will read):")
        lines += [f"    - {k}: {v}" for k, v in rec.artifacts.items()]
    if rec.preconditions:
        lines.append("  verify before accepting:")
        lines += [f"    - {p}" for p in rec.preconditions]
    lines.append(
        "  -> accept to dispatch, or decline to drop it. "
        "No agent dispatches another on its own."
    )
    return "\n".join(lines)


@runtime_checkable
class HandoffApprover(Protocol):
    def decide(self, recommendation: HandoffRecommendation) -> bool: ...


class HoldForHuman:
    """Default: never auto-accept. The human is the circuit-breaker."""

    def decide(self, recommendation: HandoffRecommendation) -> bool:
        return False


@dataclass
class CallbackHandoffApprover:
    """Programmatic approval for automation or tests."""

    fn: Callable[[HandoffRecommendation], bool]

    def decide(self, recommendation: HandoffRecommendation) -> bool:
        return bool(self.fn(recommendation))
