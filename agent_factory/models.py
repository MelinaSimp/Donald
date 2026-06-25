"""Domain models, the spawn state machine, and the structured schemas.

This module is deliberately free of I/O. It defines:

* :class:`State` and the legal ``_TRANSITIONS`` between states, plus
  :func:`assert_transition` which makes invalid transitions fail *loudly*.
* The Pydantic schemas the LLM is forced to emit (:class:`SkillsReport`)
  and the manifest a spawned agent is built from (:class:`ProposedManifest`).
* Plain row models for the three tables.
"""

from __future__ import annotations

import enum
import re
from typing import Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #


class State(str, enum.Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    DRAFTING_SPEC = "drafting_spec"
    WRITING_PROMPT = "writing_prompt"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


_TRANSITIONS: dict[State, set[State]] = {
    State.PENDING: {State.RESEARCHING, State.FAILED},
    State.RESEARCHING: {State.DRAFTING_SPEC, State.FAILED},
    State.DRAFTING_SPEC: {State.WRITING_PROMPT, State.FAILED},
    State.WRITING_PROMPT: {State.AWAITING_APPROVAL, State.FAILED},
    State.AWAITING_APPROVAL: {
        State.APPROVED,
        State.REJECTED,
        State.WRITING_PROMPT,  # reject-with-feedback rolls back to regenerate
        State.FAILED,
    },
    State.APPROVED: set(),  # terminal
    State.REJECTED: set(),  # terminal
    State.FAILED: set(),  # terminal
}

TERMINAL_STATES = frozenset(s for s, nxt in _TRANSITIONS.items() if not nxt)


class InvalidTransition(Exception):
    """Raised when a state transition is not permitted by the machine."""


def assert_transition(src: State, dst: State) -> None:
    """Refuse invalid transitions loudly, not silently."""
    if dst not in _TRANSITIONS.get(src, set()):
        raise InvalidTransition(f"illegal transition {src.value} -> {dst.value}")


# --------------------------------------------------------------------------- #
# Structured LLM output schemas (Tier 1)
# --------------------------------------------------------------------------- #


class Source(BaseModel):
    url: str
    title: str
    excerpt: str = Field(default="", max_length=400)


class ToolWishlistEntry(BaseModel):
    name: str  # proposed tool name
    purpose: str  # why this agent needs it
    external_dependency: str = ""  # API, library, service


class SkillsReport(BaseModel):
    domain: str
    competencies: list[str] = Field(min_length=1)  # 4-8 concrete capabilities
    tools_available: list[str] = Field(default_factory=list)  # names from the catalog
    tools_wishlist: list[ToolWishlistEntry] = Field(default_factory=list)
    design_patterns: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)  # 5-15 cited sources


# --------------------------------------------------------------------------- #
# Manifest (the thing a human approves)
# --------------------------------------------------------------------------- #


class ProposedManifest(BaseModel):
    slug: str
    name: str
    specialty: str
    system_prompt: str
    tool_allowlist: list[str] = Field(default_factory=list)
    model: str


# --------------------------------------------------------------------------- #
# Row models
# --------------------------------------------------------------------------- #


class ResearchReport(BaseModel):
    id: str
    query: str
    normalized_query: str
    report: SkillsReport
    created_at: str


class SpawnTask(BaseModel):
    id: str
    requested_by: str
    name_hint: str
    role_description: str
    special_requirements: Optional[str] = None
    status: State = State.PENDING
    research_report_id: Optional[str] = None
    proposed_manifest: Optional[ProposedManifest] = None
    approval_iterations: int = 0
    revision_feedback: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""


class SpawnedAgent(BaseModel):
    id: str
    slug: str
    name: str
    specialty: str
    system_prompt: str
    tool_allowlist: list[str]
    model: str
    status: str = "active"  # 'active' | 'archived'
    created_by_task_id: Optional[str] = None
    created_at: str = ""


# --------------------------------------------------------------------------- #
# Slug helpers
# --------------------------------------------------------------------------- #

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Turn a name hint into a stable, dispatch-safe slug."""
    slug = _SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return slug or "agent"
