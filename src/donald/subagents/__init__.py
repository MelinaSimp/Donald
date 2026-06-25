"""Donald's specialist sub-agents.

Each sub-agent is a focused persona with a restricted tool set. This
module is the canonical registration site; the self-knowledge sub-agents
generator renders from :func:`all_subagents`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class SubAgent:
    """A specialist persona with a name, a role, and an allowed tool set."""

    name: str
    role: str
    tools: Tuple[str, ...]


SUBAGENTS: List[SubAgent] = [
    SubAgent(
        name="researcher",
        role="Gathers and synthesizes information from the web.",
        tools=("web_search", "calculator"),
    ),
    SubAgent(
        name="scribe",
        role="Drafts and sends written communication.",
        tools=("send_email", "echo"),
    ),
]


def all_subagents() -> List[SubAgent]:
    """Return every registered sub-agent, in declaration order."""
    return list(SUBAGENTS)
